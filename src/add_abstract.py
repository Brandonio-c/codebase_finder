import argparse
import os
import bibtexparser
import requests
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase

def fetch_abstract(doi):
    url = f"https://doi.org/{doi}"
    headers = {"Accept": "application/vnd.citationstyles.csl+json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get("abstract")
    else:
        print(f"Could not fetch abstract for DOI: {doi}")
        return None

def add_abstracts_to_bibtex(input_file, output_folder):
    with open(input_file, 'r') as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file)

    total_entries = len(bib_database.entries)
    updated_entries = []

    for idx, entry in enumerate(bib_database.entries, start=1):
        print(f"Processing entry {idx} of {total_entries}...")
        if 'abstract' not in entry or not entry['abstract']:
            doi = entry.get('doi')
            if doi:
                abstract = fetch_abstract(doi)
                if abstract:
                    entry['abstract'] = abstract
                    print(f"Added abstract to entry {idx}")
        
        updated_entries.append(entry)
        print(f"Finished processing entry {idx} of {total_entries}")

    # Write the updated entries to the output file
    writer = BibTexWriter()
    output_file = os.path.join(output_folder, "output_with_abstracts.bib")
    with open(output_file, 'w') as bibtex_file:
        bib_database.entries = updated_entries
        bibtex_file.write(writer.write(bib_database))
    print(f"Output written to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add abstracts to BibTeX entries.")
    parser.add_argument("--bib_file", type=str, help="Input BibTeX file.", required=True)
    parser.add_argument("--output_dir", type=str, help="Output folder for the new BibTeX file.", required=True)

    args = parser.parse_args()

    add_abstracts_to_bibtex(args.bib_file, args.output_dir)
