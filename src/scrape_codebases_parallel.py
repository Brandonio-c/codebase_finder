import argparse
import bibtexparser
import requests
from habanero import Crossref
from github import Github
from copy import deepcopy
from bs4 import BeautifulSoup
import re
from PyPDF2 import PdfReader
from googlesearch import search as google_search
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
import backoff
from threading import Lock
from datetime import datetime
from difflib import SequenceMatcher

# Ensure this token is correct and has necessary permissions
GITHUB_TOKEN = 'token'  # Ensure this token is correct and has necessary permissions  # Replace with your GitHub token

lock = Lock()  # Create a lock for thread-safe file operations

def fetch_doi(title):
    """Fetch DOI for a given title using Crossref."""
    try:
        cr = Crossref()
        result = cr.works(query_title=title, limit=1)
        if result['message']['items']:
            return result['message']['items'][0].get('DOI')
    except Exception as e:
        print(f"Error fetching DOI for title '{title}': {e}")
    return None

@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_tries=5)
def fetch_pdf_from_doi(doi):
    """Fetch the PDF of the paper using the DOI, trying to find an open version if necessary."""
    try:
        url = f"https://doi.org/{doi}"
        response = requests.get(url)
        response.raise_for_status()
        pdf_url_match = re.search(r'href="([^"]*\.pdf)"', response.text)
        if pdf_url_match:
            pdf_url = pdf_url_match.group(1)
            if not pdf_url.startswith('http'):
                pdf_url = f"https:{pdf_url}"
            pdf_response = requests.get(pdf_url)
            pdf_response.raise_for_status()
            return BytesIO(pdf_response.content)
    except requests.exceptions.RequestException as e:
        if response.status_code == 418:
            return fetch_open_version(doi)
        print(f"Error fetching PDF from DOI '{doi}': {e}")
    return None

def fetch_open_version(doi):
    """Try to find an open access version of the paper, such as on arXiv."""
    try:
        cr = Crossref()
        result = cr.works(ids=doi)
        if 'URL' in result['message']:
            response = requests.get(result['message']['URL'])
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            open_access_links = soup.find_all('a', href=True)
            for link in open_access_links:
                if 'arxiv.org' in link['href']:
                    return fetch_pdf_from_url(link['href'])
    except Exception as e:
        print(f"Error fetching open version for DOI '{doi}': {e}")
    return None

@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_tries=5)
def fetch_pdf_from_url(url):
    """Fetch the PDF of the paper using a URL."""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        response = requests.get(url)
        response.raise_for_status()
        pdf_response = requests.get(response.url)
        pdf_response.raise_for_status()
        return BytesIO(pdf_response.content)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching PDF from URL '{url}': {e}")
    return None

def skim_pdf_for_links(pdf_file):
    """Skim the PDF for links to codebases."""
    links = []
    try:
        reader = PdfReader(pdf_file)
        for page in reader.pages:
            text = page.extract_text()
            links.extend(re.findall(r'(https?://\S+)', text))
        return links
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return []

@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_tries=5)
def search_github(title, authors, year, check_author, debug):
    """Search GitHub for the project online code base."""
    try:
        github = Github(GITHUB_TOKEN)
        results = github.search_repositories(query=title, sort='stars', order='desc')
        if results.totalCount > 0:
            for repo in results:
                if validate_repository(repo.html_url, title, authors, year, check_author, debug, repo):
                    return repo.html_url
    except Exception as e:
        if hasattr(e, 'status') and e.status == 403 and 'rate limit exceeded' in str(e):
            if debug:
                print("Rate limit exceeded, sleeping for 60 seconds...")
            time.sleep(60)
            return search_github(title, authors, year, check_author, debug)
        if hasattr(e, 'status') and e.status == 401:
            if debug:
                print(f"Error searching GitHub for title '{title}': Bad credentials. Check your GITHUB_TOKEN.")
        else:
            if debug:
                print(f"Error searching GitHub for title '{title}': {e}")
    return None

def title_similarity(title1, title2):
    """Calculate the similarity ratio between two titles."""
    return SequenceMatcher(None, title1, title2).ratio()

def validate_repository(repo_url, title, authors, year, check_author, debug, repo_obj=None):
    """Validate if the URL points to a repository containing code relevant to the title, and optionally check authorship and year."""
    try:
        response = requests.get(repo_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Check for repository content and title relevance
            readme = soup.find('article', {'class': 'markdown-body entry-content container-lg'})
            if readme:
                readme_text = readme.text.lower()
                title_words = title.lower().split()
                num_title_words = len(title_words)
                matched_words = sum(1 for word in title_words if word in readme_text)
                similarity_ratio = matched_words / num_title_words

                if similarity_ratio >= 0.9:
                    if year and repo_obj and repo_obj.updated_at.year > year:
                        if debug:
                            print(f"Repository '{repo_url}' rejected for title '{title}': updated later than paper's publication year.")
                        return False
                    if check_author and authors:
                        repo_authors = [a.get_text() for a in soup.select('.commit-author')]
                        if not any(author in repo_authors for author in authors):
                            if debug:
                                print(f"Repository '{repo_url}' rejected for title '{title}': authors do not match.")
                            return False
                    return True
                else:
                    if debug:
                        print(f"Repository '{repo_url}' rejected for title '{title}': title not found in repository content with sufficient similarity (ratio: {similarity_ratio:.2f}).")
            else:
                if debug:
                    print(f"Repository '{repo_url}' rejected for title '{title}': readme not found in repository content.")
        else:
            if debug:
                print(f"Repository '{repo_url}' rejected for title '{title}': failed to fetch content, status code {response.status_code}.")
    except Exception as e:
        if debug:
            print(f"Error validating repository at '{repo_url}' for title '{title}': {e}")
    return False

def search_paperswithcode(title, authors, year, check_author, debug):
    """Search PapersWithCode for the project online code base."""
    try:
        url = f"https://paperswithcode.com/api/v1/search/?q={title}"
        response = requests.get(url)
        response.raise_for_status()
        results = response.json()
        if results.get('results'):
            for paper in results['results']:
                if paper.get('repository') and paper['repository'].get('url'):
                    repo_url = paper['repository']['url']
                    if validate_repository(repo_url, title, authors, year, check_author, debug):
                        return repo_url
    except Exception as e:
        if debug:
            print(f"Error searching PapersWithCode for title '{title}': {e}")
    return None

def search_huggingface(title, authors, year, check_author, debug):
    """Search Hugging Face for the project online code base."""
    try:
        base_url = "https://huggingface.co/models?search="
        search_url = base_url + title.replace(" ", "+")
        response = requests.get(search_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        model_cards = soup.find_all('div', class_='model-card')
        if model_cards:
            for card in model_cards:
                card_url = card.find('a', href=True)
                if card_url and validate_repository(card_url['href'], title, authors, year, check_author, debug):
                    return card_url['href']
    except Exception as e:
        if debug:
            print(f"Error searching Hugging Face for title '{title}': {e}")
    return None

def search_zenodo(title, authors, year, check_author, debug):
    """Search Zenodo for the project online code base."""
    try:
        search_url = f"https://zenodo.org/search?page=1&size=20&q={title.replace(' ', '+')}&type=software"
        response = requests.get(search_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('a', class_='result-item-title')
        for result in results:
            repo_url = result['href']
            if validate_repository(repo_url, title, authors, year, check_author, debug):
                return repo_url
    except Exception as e:
        if debug:
            print(f"Error searching Zenodo for title '{title}': {e}")
    return None

def search_figshare(title, authors, year, check_author, debug):
    """Search Figshare for the project online code base."""
    try:
        search_url = f"https://figshare.com/search?q={title.replace(' ', '+')}&searchMode=1"
        response = requests.get(search_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('a', class_='search-result')
        for result in results:
            repo_url = result['href']
            if validate_repository(repo_url, title, authors, year, check_author, debug):
                return repo_url
    except Exception as e:
        if debug:
            print(f"Error searching Figshare for title '{title}': {e}")
    return None

def search_openreview(title, authors, year, check_author, debug):
    """Search OpenReview for the project online code base."""
    try:
        search_url = f"https://openreview.net/search?q={title.replace(' ', '+')}"
        response = requests.get(search_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('a', class_='note_content_title')
        for result in results:
            repo_url = result['href']
            if validate_repository(repo_url, title, authors, year, check_author, debug):
                return repo_url
    except Exception as e:
        if debug:
            print(f"Error searching OpenReview for title '{title}': {e}")
    return None

def search_codeocean(title, authors, year, check_author, debug):
    """Search CodeOcean for the project online code base."""
    try:
        search_url = f"https://codeocean.com/explore?query={title.replace(' ', '+')}&scope=all&order=relevance"
        response = requests.get(search_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('a', class_='paper-title')
        for result in results:
            repo_url = result['href']
            if validate_repository(repo_url, title, authors, year, check_author, debug):
                return repo_url
    except Exception as e:
        if debug:
            print(f"Error searching CodeOcean for title '{title}': {e}")
    return None

def search_mendeley_data(title, authors, year, check_author, debug):
    """Search Mendeley Data for the project online code base."""
    try:
        search_url = f"https://data.mendeley.com/search?query={title.replace(' ', '+')}"
        response = requests.get(search_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('a', class_='search-result-title')
        for result in results:
            repo_url = result['href']
            if validate_repository(repo_url, title, authors, year, check_author, debug):
                return repo_url
    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 404:
            pass
        else:
            if debug:
                print(f"HTTP error occurred: {http_err}")
    except Exception as e:
        if debug:
            print(f"Error searching Mendeley Data for title '{title}': {e}")
    return None

def web_search(title, authors, year, check_author, debug):
    """Search the web for the project online code base."""
    try:
        search_query = f"{title} code repository"
        search_results = google_search(search_query, num_results=5)
        for result in search_results:
            if validate_repository(result, title, authors, year, check_author, debug):
                return result
    except Exception as e:
        if debug:
            print(f"Error performing web search for title '{title}': {e}")
    return None

def add_doi_to_entry(entry):
    if 'doi' not in entry:
        doi = fetch_doi(entry.get('title', ''))
        if doi:
            entry['doi'] = doi

def find_codebase_link(entry, check_paper, search_web, check_author, debug):
    title = entry.get('title', '')
    doi = entry.get('doi', '')
    year = None
    if 'year' in entry:
        try:
            year = int(entry['year'])
        except ValueError:
            pass
    authors = entry.get('author', '').split(' and ')
    platforms = [search_paperswithcode, search_github, search_huggingface, 
                 search_zenodo, search_figshare, 
                 search_openreview, search_codeocean, search_mendeley_data]
    
    # Check codebase links from platforms
    for platform in platforms:
        link = platform(title, authors, year, check_author, debug)
        if link:
            return link
    
    # Skim PDF for codebase links if option is enabled
    if check_paper and doi:
        pdf_file = fetch_pdf_from_doi(doi)
        if pdf_file:
            links = skim_pdf_for_links(pdf_file)
            for link in links:
                if validate_repository(link, title, authors, year, check_author, debug):
                    return link
    
    # Perform web search for codebase links if option is enabled
    if search_web:
        link = web_search(title, authors, year, check_author, debug)
        if link:
            return link
    
    return "No codebase found"

def save_bib_files(with_code, without_code, output_dir):
    with lock:
        with open(os.path.join(output_dir, 'with_code.bib'), 'w', encoding='utf-8') as bibtex_file:
            bibtexparser.dump(with_code, bibtex_file)
        with open(os.path.join(output_dir, 'without_code.bib'), 'w', encoding='utf-8') as bibtex_file:
            bibtexparser.dump(without_code, bibtex_file)

def process_entry(entry, with_code, without_code, check_paper, search_web, check_author, output_dir, debug):
    try:
        add_doi_to_entry(entry)
        codebase_link = find_codebase_link(entry, check_paper, search_web, check_author, debug)
        if codebase_link and codebase_link != "No codebase found":
            entry['url'] = codebase_link
            with_code.entries.append(entry)
        else:
            without_code.entries.append(entry)
        
        save_bib_files(with_code, without_code, output_dir)
        return entry
    except Exception as e:
        if debug:
            print(f"Error processing entry '{entry.get('title', 'No Title')}': {e}")
        return entry

def process_bibtex(file_path, check_paper, search_web, check_author, num_threads, output_dir, debug):
    try:
        with open(file_path, 'r', encoding='utf-8') as bibtex_file:
            bib_database = bibtexparser.load(bibtex_file)
        
        with_code = deepcopy(bib_database)
        without_code = deepcopy(bib_database)
        with_code.entries = []
        without_code.entries = []

        total_entries = len(bib_database.entries)
        futures = []
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            for idx, entry in enumerate(bib_database.entries, start=1):
                print(f"Processing entry {idx}/{total_entries}: {entry.get('title', 'No Title')}")
                futures.append(executor.submit(process_entry, entry, with_code, without_code, check_paper, search_web, check_author, output_dir, debug))
            
            for future in as_completed(futures):
                future.result()
                print(f"Completed entry {len(with_code.entries) + len(without_code.entries)}/{total_entries}")

    except Exception as e:
        print(f"Error processing BibTeX file '{file_path}': {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process a BibTeX file to add DOIs and categorize entries based on the availability of codebases.')
    parser.add_argument('--bib_file', required=True, help='Path to the BibTeX file')
    parser.add_argument('--check_paper', action='store_true', help='Skim the associated paper\'s PDF for links to codebases using the DOI')
    parser.add_argument('--search_web', action='store_true', help='Search the web for codebases')
    parser.add_argument('--check_author', action='store_true', help='Check if the author of the codebase is one of the authors of the paper')
    parser.add_argument('--num_threads', type=int, default=4, help='Number of threads to run in parallel')
    parser.add_argument('--output_dir', required=True, help='Directory to save the output BibTeX files')
    parser.add_argument('--debug_valid_repo', action='store_true', help='Print debug statements during repository validation')

    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    process_bibtex(args.bib_file, args.check_paper, args.search_web, args.check_author, args.num_threads, args.output_dir, args.debug_valid_repo)
