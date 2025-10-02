import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import quote
import brotli
import gzip
from io import BytesIO

def scrape_tijori_finance_stock_data(symbol, exchange="NSE", broker="kite", theme=""):
    """
    Scrape financial data from Tijori Finance B2B widget
    
    Args:
        symbol (str): Stock symbol (e.g., "BEL", "RELIANCE", "TCS")
        exchange (str): Exchange name (default: "NSE")
        broker (str): Broker name (default: "kite")  
        theme (str): Theme parameter (default: "")
    
    Returns:
        dict: Dictionary with financial metrics in the format:
              {'symbol': 'RELIANCE', 'pe': 25, 'pb': 3, 'de': 0.7, 'roe': 17, 
               'eps_growth': 12, 'div_yield': 1.5, 'operating_margin': 20, 'interest_coverage': 6}
    """
    
    # Construct the Tijori Finance B2B widget URL
    base_url = "https://b2b.tijorifinance.com/b2b/v1/in/kite-widget/web/equity/"
    url = f"{base_url}{symbol}/?exchange={exchange}&broker={broker}&theme={theme}"
    
    # Headers to mimic a real browser request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"'
    }
    
    # Initialize result dictionary
    result = {
        'symbol': symbol.upper(),
        'pe': None,
        'pb': None, 
        'de': None,
        'roe': None,
        'eps_growth': None,
        'div_yield': None,
        'operating_margin': None,
        'interest_coverage': None
    }
    
    try:
        print(f"Scraping Tijori Finance for {symbol}...")
        
        # Make the request with timeout
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            # Handle compressed content (brotli, gzip, etc.)
            content = ""
            content_encoding = response.headers.get('content-encoding', '').lower()
            
            if 'br' in content_encoding:
                # Brotli compression
                try:
                    content = brotli.decompress(response.content).decode('utf-8')
                    print("Successfully decompressed brotli content")
                except Exception as e:
                    print(f"Brotli decompression failed: {e}")
                    content = response.text
            elif 'gzip' in content_encoding:
                # Gzip compression
                try:
                    content = gzip.decompress(response.content).decode('utf-8')
                    print("Successfully decompressed gzip content")
                except:
                    content = response.text
            else:
                content = response.text
            
            # Parse HTML content
            soup = BeautifulSoup(content, 'html.parser')
            
            # Method 1: Look for JSON data in script tags
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    script_content = script.string
                    
                    # Look for financial data patterns in JavaScript
                    if any(term in script_content.lower() for term in ['pe', 'pb', 'roe', 'financial', 'ratio']):
                        try:
                            # Extract numerical values for financial metrics
                            pe_match = re.search(r'pe["\'\s]*:?\s*["\']?(\d+\.?\d*)', script_content, re.IGNORECASE)
                            pb_match = re.search(r'pb["\'\s]*:?\s*["\']?(\d+\.?\d*)', script_content, re.IGNORECASE)
                            roe_match = re.search(r'roe["\'\s]*:?\s*["\']?(\d+\.?\d*)', script_content, re.IGNORECASE)
                            
                            if pe_match and not result['pe']:
                                result['pe'] = float(pe_match.group(1))
                            if pb_match and not result['pb']:
                                result['pb'] = float(pb_match.group(1))
                            if roe_match and not result['roe']:
                                result['roe'] = float(roe_match.group(1))
                                
                        except Exception as e:
                            print(f"Error parsing script content: {e}")
            
            # Method 2: Look for specific HTML elements with financial data
            financial_elements = soup.find_all(['td', 'span', 'div', 'p'], 
                                             string=re.compile(r'P/E|PE.*Ratio|Price.*Earnings', re.IGNORECASE))
            
            for element in financial_elements:
                try:
                    # Find the associated value in nearby elements
                    value_element = (element.find_next_sibling() or 
                                   element.parent.find_next_sibling() or
                                   element.find_next())
                    
                    if value_element:
                        value_text = value_element.get_text().strip()
                        pe_match = re.search(r'(\d+\.?\d*)', value_text)
                        if pe_match and not result['pe']:
                            pe_val = float(pe_match.group(1))
                            if 1 < pe_val < 1000:  # Reasonable PE range
                                result['pe'] = pe_val
                                break
                except:
                    pass
            
            print(f"Tijori Finance scraping completed for {symbol}")
            
        else:
            print(f"Failed to fetch data: HTTP {response.status_code}")
            
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        
    except Exception as e:
        print(f"Scraping error: {e}")
    
    # If Tijori scraping didn't get all data, try fallback sources
    if any(v is None for v in result.values() if v != result['symbol']):
        print("Some data missing, trying fallback sources...")
        fallback_result = scrape_fallback_sources(symbol)
        
        # Merge results, preferring Tijori data where available
        for key, value in fallback_result.items():
            if result[key] is None and value is not None:
                result[key] = value
    
    return result

def scrape_fallback_sources(symbol):
    """
    Fallback method using multiple reliable sources for NSE stock data
    """
    result = {
        'symbol': symbol.upper(),
        'pe': None,
        'pb': None,
        'de': None,
        'roe': None,
        'eps_growth': None,
        'div_yield': None,
        'operating_margin': None,
        'interest_coverage': None
    }
    
    print(f"Trying fallback sources for {symbol}...")
    
    # Source 1: Try Screener.in (most reliable for Indian stocks)
    try:
        screener_url = f"https://www.screener.in/company/{symbol}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(screener_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for the ratios table
            ratio_sections = soup.find_all(['table', 'div'], class_=re.compile(r'ratios|financials|data', re.IGNORECASE))
            
            for section in ratio_sections:
                rows = section.find_all('tr') if section else []
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        metric_name = cells[0].get_text().strip().lower()
                        metric_value = cells[1].get_text().strip()
                        
                        # Extract numerical value
                        value_match = re.search(r'(\d+\.?\d*)', metric_value.replace(',', ''))
                        if value_match:
                            value = float(value_match.group(1))
                            
                            if ('pe' in metric_name or 'price' in metric_name and 'earnings' in metric_name) and not result['pe']:
                                if 1 < value < 1000:
                                    result['pe'] = value
                            elif ('pb' in metric_name or 'price' in metric_name and 'book' in metric_name) and not result['pb']:
                                if 0.1 < value < 100:
                                    result['pb'] = value
                            elif 'roe' in metric_name and not result['roe']:
                                if 0 < value < 100:
                                    result['roe'] = value
                            elif 'debt' in metric_name and 'equity' in metric_name and not result['de']:
                                result['de'] = value
                            elif 'dividend' in metric_name and 'yield' in metric_name and not result['div_yield']:
                                result['div_yield'] = value
                                
            print(f"Screener.in data extracted for {symbol}")
                                
    except Exception as e:
        print(f"Screener.in scraping failed: {e}")
    
    # Source 2: Try Economic Times (backup)
    try:
        # Economic Times URL pattern varies, this is a generic approach
        et_search_url = f"https://economictimes.indiatimes.com/markets/stocks/fno"
        # Implementation would be more complex for ET due to dynamic content
    except Exception as e:
        print(f"Economic Times scraping failed: {e}")
    
    # LET US NOT USE FALLBACK VALUES, IF NOT KNOWN, WE WON'T TRADE IN THIS
    # Add known values for common stocks as ultimate fallback
    # stock_fallbacks = {
    #     'BEL': {
    #         'pe': 53.68,
    #         'pb': 14.62, 
    #         'de': 0.00,
    #         'roe': 26.64,
    #         'div_yield': 0.59,
    #         'operating_margin': 31.87,
    #         'interest_coverage': 782.65,
    #         'eps_growth': 23.8  # 5-year CAGR from search results
    #     },
    #     'RELIANCE': {
    #         'pe': 25.2,
    #         'pb': 2.8,
    #         'de': 0.7,
    #         'roe': 17.5,
    #         'div_yield': 1.5,
    #         'operating_margin': 20.1,
    #         'interest_coverage': 6.2,
    #         'eps_growth': 12.3
    #     }
    # }
    
    # if symbol.upper() in stock_fallbacks:
    #     fallback_values = stock_fallbacks[symbol.upper()]
    #     print(f"Using fallback data for {symbol}")
        
    #     for key, fallback_val in fallback_values.items():
    #         if result[key] is None:
    #             result[key] = fallback_val
    
    return result

def validate_and_clean_result(result):
    """
    Validate and clean the result data
    """
    # Ensure all values are reasonable
    if result['pe'] and (result['pe'] < 1 or result['pe'] > 1000):
        result['pe'] = None
    if result['pb'] and (result['pb'] < 0.1 or result['pb'] > 100):
        result['pb'] = None
    if result['roe'] and (result['roe'] < 0 or result['roe'] > 100):
        result['roe'] = None
    if result['de'] and result['de'] < 0:
        result['de'] = None
    if result['div_yield'] and (result['div_yield'] < 0 or result['div_yield'] > 50):
        result['div_yield'] = None
    if result['operating_margin'] and (result['operating_margin'] < -100 or result['operating_margin'] > 100):
        result['operating_margin'] = None
    if result['interest_coverage'] and result['interest_coverage'] < 0:
        result['interest_coverage'] = None
    
    return result

def main():
    """
    Main function to demonstrate usage
    """
    # Example usage
    test_symbols = ["BEL", "RELIANCE", "TCS"]
    
    for symbol in test_symbols[:1]:  # Test with first symbol only
        print(f"\n{'='*50}")
        print(f"Scraping financial data for {symbol}")
        print(f"{'='*50}")
        
        financial_data = scrape_tijori_finance_stock_data(symbol)
        financial_data = validate_and_clean_result(financial_data)
        
        print(f"\nResults for {symbol}:")
        print(json.dumps(financial_data, indent=2, default=str))
        
        # Check if we have the required format
        required_keys = ['symbol', 'pe', 'pb', 'de', 'roe', 'eps_growth', 'div_yield', 'operating_margin', 'interest_coverage']
        missing_keys = [key for key in required_keys if key not in financial_data]
        
        if missing_keys:
            print(f"\nWarning: Missing keys: {missing_keys}")
        else:
            print(f"\nâœ“ All required keys present for {symbol}")
    
    # Show the exact required output format
    print(f"\n{'='*50}")
    print("REQUIRED OUTPUT FORMAT EXAMPLE:")
    print(f"{'='*50}")
    required_format = {
        'symbol': 'RELIANCE', 
        'pe': 25, 
        'pb': 3, 
        'de': 0.7, 
        'roe': 17, 
        'eps_growth': 12,  
        'div_yield': 1.5, 
        'operating_margin': 20, 
        'interest_coverage': 6
    }
    print(json.dumps(required_format, indent=2))

if __name__ == "__main__":
    main()