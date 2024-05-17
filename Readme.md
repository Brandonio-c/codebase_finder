Overview
This project is designed to scrape and enrich bibliographic entries with additional metadata, such as abstracts and codebase links. The workflow involves running Python scripts to process .bib files, using a combination of APIs and web scraping techniques to gather the necessary information.

Folder Structure
src/: Contains the main Python scripts.
add_abstract.py: Script to add abstracts to bibliographic entries.
scrape_codebases_parallel.py: Script to scrape codebases and enrich bibliographic entries.
data/: Contains input .bib files.
output/: Directory where the processed files will be saved.
scripts/: Contains shell scripts to run the Python scripts with specific SLURM configurations.
run_add_abstract.sh
run_codebase_scraper.sh
Requirements
The project requires the following Python packages:

argparse
bibtexparser
requests
habanero
PyGithub
beautifulsoup4
PyPDF2
googlesearch-python
ratelimit==2.2.1
backoff==1.11.1
You can install these dependencies using pip:

Usage
Scraping Codebases
To scrape codebases and enrich your bibliographic entries, use the scrape_codebases_parallel.py script. You can run this script using the provided SLURM script run_codebase_scraper.sh.

Adding Abstracts
To add abstracts to your bibliographic entries, use the add_abstract.py script. You can run this script using the provided SLURM script run_add_abstract.sh.

Contributing
Please ensure that you have the necessary dependencies installed and follow the existing coding style. Contributions are welcome via pull requests.

License
This project is licensed under the MIT License. See the LICENSE file for more details.