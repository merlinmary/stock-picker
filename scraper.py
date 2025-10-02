from tijori_scraper import scrape_tijori_finance

# Scrape BEL data
bel_data = scrape_tijori_finance("BEL")
print(bel_data)

# Scrape RELIANCE data  
reliance_data = scrape_tijori_finance("RELIANCE")
print(reliance_data)