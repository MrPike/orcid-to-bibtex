import json
from collections import defaultdict
from argparse import Namespace, ArgumentParser
from asyncio import Semaphore, run, gather

from aiohttp import ClientSession, TCPConnector
from pathlib import Path
import bibtexparser as bp
import yake
from doi2bib import crossref

import logging

_log = logging.getLogger(__name__)


async def get_orcid(
    orcid_path: str, session: ClientSession, dl_limit: Semaphore
) -> json:
    """
    Retrieves a single item from the ORCID API endpoint.
    :param orcid_path: The ORCID API path (not include base domain) for the desired item
    :param session: AIOHTTP session for the application
    :param dl_limit: Semaphore controlling the number of simultaneous connections to the ORCID API
    :return: JSON response returned from the ORCID API
    """
    async with dl_limit:
        async with session.get(
            f"https://pub.orcid.org/{orcid_path}",
            headers={"Accept": "application/orcid+json"},
        ) as response:
            if (
                response.status == 200
                and response.content_type == "application/orcid+json"
            ):
                return await response.json()
            else:
                _log.error(
                    f"Response status is {response.status}, content type is {response.content_type}"
                )


async def get_orcid_works(
    orcid_id: str, max_dls: int = 50, validate_ssl: bool = True
) -> list[str]:
    """
    Retrieves all works associated with the provided ORCID ID. Returns a string in BibTeX format. Note,
    that the resulting BibTeX returned by this function will likely contain duplicate keys.

    :param orcid_id: ORCID ID of the user's whose works are to be retrieved.
    :param max_dls: Maximum concurrent download workers made to ORCID's API.
    :param validate_ssl: Whether SSL certificates should be validated.
    :return: A collection of BibTeX strings for each work retrieved from ORCID. Contains duplicate keys.
    """
    dl_limit = Semaphore(max_dls)
    async with ClientSession(connector=TCPConnector(ssl=validate_ssl)) as session:
        # Get the list of all user's works
        works = await get_orcid(f"{orcid_id}/works", session, dl_limit)
        urls = []
        # For each work, generate the API path needed in order to retrieve all details
        for work in works["group"]:
            urls.append(work["work-summary"][0]["path"])
        # Get details for all works
        results = await gather(*[get_orcid(url, session, dl_limit) for url in urls])
        bib = []
        # Extract BibTeX provided by ORCID
        for work in results:
            assert work and "citation" in work
            # TODO: Is this ever not set in work?
            title = work["title"]["title"]["value"]
            _log.debug(f"Now working on {title}")
            _log.debug(
                f"citation is None? {'yes' if work['citation'] is None else 'no'}"
            )
            if work.get("citation", None) is not None:
                _log.debug(f"citation-type is {work['citation']['citation-type']}")
            if (
                work["citation"] is None
                or work["citation"].get("citation-type", None) != "bibtex"
            ):
                # TODO: Deal with "formatted-unspecified" citation types.
                _log.debug(
                    f'No appropriate citation found in response for "{title}". Fetching via crossref...'
                )
                if work["external-ids"] is None:
                    _log.warning(
                        f'No external ids associated with "{title}"! Cannot fetch bib from doi.'
                    )
                doi = None
                for id in work["external-ids"]["external-id"]:
                    if id["external-id-type"] == "doi":
                        doi = id["external-id-value"]
                        found, bi = crossref.get_bib(doi)
                        if not found:
                            _log.warning(f"Nothing found for doi {doi}!")
                        else:
                            bib.append(bi)
                            _log.debug(f"Bib entry for doi {doi} added.")
                        break
                if doi is None:
                    _log.warning(f"No doi found in external ids! Cannot fetch bib.")
            else:
                bib.append(work["citation"]["citation-value"])
                _log.debug(f"Bib entry added from response.")

        return bib


def parse_and_format_bib(
    input_bib: str, indent: int = 4, order_by: tuple = ("id",)
) -> None:
    """
    Parses and formats BibTeX, writes it to file. Intelligently renames BibTeX IDs according to each entry's title,
    using keyword extraction.
    :param input_bib: String containing non-formatted (and likely duplicate keys) BibTeX
    :param out_bib: The formatted BibTeX string
    :param indent: Formatting option: number of spaces to indent each entry's fields
    :param order_by: Formatting option: fields by which, entries should be ordered
    """

    db = bp.loads(input_bib)

    # Dict is used to count and check for duplicate keys in the generated BibTeX file
    bib_id_count = defaultdict(int)
    for e in db.entries:
        # Remove all non-alphanumeric characters from the title, apart from spaces
        title = "".join(
            [
                character
                for character in e["title"]
                if character.isalpha() or character.isspace()
            ]
        )
        keywords = yake.KeywordExtractor().extract_keywords(title)
        bibtex_id = e["ID"]

        # Intelligent renaming of BibTeX entry keys based on the title of the work.
        # Keywords extracted from the title are added to the key until a unique key is generated. If keywords are
        # exhausted and the resulting key is still not unique, then the instance number for that key is appended.
        unique, c = False, 0
        while not unique:
            if c < len(keywords):
                bibtex_id += "_" + keywords[c][0].replace(" ", "_").title()
                if bibtex_id not in bib_id_count:
                    bib_id_count[bibtex_id] += 1
                    unique = True
            else:
                bib_id_count[bibtex_id] += 1
                bibtex_id += bibtex_id + "_" + str(bib_id_count)

        e["ID"] = bibtex_id

    # Write the formatted BibTeX to file
    writer = bp.bwriter.BibTexWriter()
    writer.indent = " " * indent  # indent entries with
    writer.order_entries_by = order_by

    return writer.write(db)


def parse_cli_args() -> Namespace:
    """
    Argument parser for the application
    :return: An object containing the user specified arguments
    """
    p = ArgumentParser(description="Generates a BibTeX file for a given ORCID id.")
    p.add_argument(
        "ORCID", type=str, metavar="0000-0000-0000-0000", help="Individual's ORCID ID."
    )
    p.add_argument(
        "-o",
        type=Path,
        metavar="PATH",
        help="The output path of the generated BibTeX file.",
    )
    p.add_argument(
        "--dl",
        type=int,
        metavar="MAX_DL",
        default=50,
        help="The maximum number of concurrent connections to ORCID's servers.",
    )
    p.add_argument(
        "--orderby",
        type=str,
        nargs="+",
        metavar="ORDER_BY",
        default="year",
        help="How entries should be ordered/sorted. Default = Order by year of publication.",
    )
    p.add_argument(
        "--indent",
        type=int,
        metavar="INDENT",
        default=4,
        help="How many spaces should each field be indented by?",
    )
    p.add_argument(
        "--no_ssl",
        action="store_true",
        help="Do not validate SSL certificates when connecting to ORCID's API.",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Print debug information.",
    )

    args = p.parse_args()
    if args.o is None:
        args.o = Path(args.ORCID + ".bib")

    if args.orderby is None:
        args.orderby = ("id",)
    else:
        args.orderby = tuple(args.orderby)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    return args


async def main() -> None:
    args = parse_cli_args()
    bib = "".join(
        await get_orcid_works(args.ORCID, max_dls=args.dl, validate_ssl=not args.no_ssl)
    )
    args.o.write_text(
        parse_and_format_bib(bib, indent=args.indent, order_by=args.orderby)
    )


if __name__ == "__main__":
    run(main())
