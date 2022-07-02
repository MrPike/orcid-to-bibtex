# ORCID to BibTeX
Command-line program which generates a BibTeX file from an individual's ORCID record.

## Features

+ Concurrent downloading of works from ORCID using [AIOHTTP](https://docs.aiohttp.org/en/stable/)
+ Intelligent renaming of BibTeX keys (to avoid duplicates) using keyword extraction ([YAKE](https://github.com/LIAAD/yake))on work titles


## Usage
Clone this repository to your local machine using git:
```shell
git clone https://github.com/MrPike/orcid-to-bibtex.git
```
Navigate into directory containing the code:
```shell
cd orcid-to-bibtex
```
Now install the application's dependencies. It's recommended that you use  [Poetry](https://python-poetry.org) to do this.
```shell
poetry install
```

Now activate a poetry shell and run the application:

```shell
poetry shell
python3 orcid-to-bibtex.py 0000-0000-0000-1234
```

Replace *0000-0000-0000-1234*,  with the ORCID id of the individual whose works you would like to retrieve.

The application supports the following arguments:

```
-o          The output path for the generated BibTeX file. A value must be specified.
--dl        The maximum number of concurrent connections to ORCID's API. The default is 50.
--orderby   How BibTeX entries should be sorted. Multiple fields can be specified. e.g. year title. The default is 'id'.
--indent    The number of spaces each field in a given entry should be indented by. The default is 4 spaces.
--ssl       Indicates whether SSL certificates should be validated or not. Default is true (meaning - certificates are validated).
```

### Example usages:

1. Get all works for the ORCID user with the ID '0000-0002-1543-0148' and save the file to 'my_pubs.bib':

```shell
python3 orcid-to-bibtex.py 0000-0002-1543-0148 -o my_pubs.bib
```

2. As with \#1 (above), but entry details should be indented by 8 spaces (instead of the default - 4) and entries sorted by publication year, then title:

```shell
python3 orcid-to-bibtex.py 0000-0002-1543-0148 -o my_pubs.bib --indent 8 --orderby year title
```