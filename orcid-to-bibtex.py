import pprint
from collections import defaultdict

from argparse import Namespace, ArgumentParser
from typing import Any
from asyncio import Semaphore, run, gather
from aiohttp import ClientSession, TCPConnector
from pathlib import Path
import bibtexparser as bp


async def get_orcid(orcid_path: str, session: ClientSession, dl_limit: Semaphore) -> Any:
    async with dl_limit:
        async with session.get(
                f"https://pub.orcid.org/{orcid_path}",
                headers={'Accept': 'application/orcid+json'}
        ) as response:
            return await response.json()


async def download_all(urls: list, session: ClientSession, dl_limit: Semaphore) -> Any:
    return await gather(*[get_orcid(url, session, dl_limit) for url in urls])


async def get_orcid_works(orcid_id: str) -> Any:
    dl_limit = Semaphore(50)
    async with ClientSession(connector=TCPConnector(ssl=False)) as session:
        works = await get_orcid(f"{orcid_id}/works", session, dl_limit)
        urls = []
        for work in works['group']:
            urls.append(work["work-summary"][0]["path"])
        results = await download_all(urls, session, dl_limit)
        bib = []
        for work in results:
            if work['citation']['citation-type'] == 'bibtex':
                bib.append(work['citation']['citation-value'].encode('utf-8'))

        '''
            A (very) hacky fix for duplicate entry keys in BibTeX.
            This will need improving, along with additional processing (formatting, validation) of the resulting
            BibTeX output. 
        '''
        bib_d = defaultdict(int)
        for i, b in enumerate(bib):
            bib_key = b.split('{')[1].split(',')[0]
            bib_d[bib_key] += 1
            if bib_d[bib_key] > 1:
                bib[i] = bib[i].replace(f"{{{bib_key},", f"{{{bib_key}_{bib_d[bib_key]},")

        return bib


def parse_and_format_bib(input_bib: Path, out_bib: Path, indent: int = 4, order_by: str | tuple = 'year') -> None:
    db = bp.loads(input_bib.read_text())

    writer = bp.bwriter.BibTexWriter()
    writer.indent = ' ' * indent  # indent entries with
    writer.order_entries_by = order_by
    out_bib.write_text(writer.write(db))


def parse_cli_args() -> Namespace:
    p = ArgumentParser(description='Generates a BibTeX file for a given ORCID id.')
    p.add_argument('ORCID', type=str, metavar='0000-0000-0000-0000',
                   help="The ORCID ID for the individual whose works should be recorded.")
    p.add_argument('-o', type=Path, metavar='PATH',
                   help="The destination for the output BibTeX file.")
    return p.parse_args()


async def main():
    args = parse_cli_args()
    orcid = args.ORCID  # Test with: '0000-0002-1543-0148'
    bib_path = args.o or Path(f'{orcid}.bib')
    bib = await get_orcid_works(orcid)
    bib_path.write_text('\n'.join(bib))


# run(main())

parse_and_format_bib(Path('0000-0002-1543-0148.bib'), Path('0000-0002-1543-0148.bib'))
