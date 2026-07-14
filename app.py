import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import random
import re

st.set_page_config(page_title="EBay-Amazon Tracker", layout="wide")

st.title("📦 eBay-Amazon Price & Stock Monitor")
st.write("Upload your Excel/CSV file containing SKUs and Amazon UK/US URLs.")

uploaded_file = st.file_uploader("Choose a file (Excel or CSV)", type=["xlsx", "csv"])

def parse_amazon_page(url):
    # Convert standard desktop URLs to mobile layouts to bypass heavy firewalls
    url = url.replace("www.amazon", "www.amazon") # fallback base
    if "/dp/" in url:
        url = re.sub(r'amazon\.(co\.uk|com)/[^/]+/dp/', r'amazon.\1/dp/', url)

    # Mimic a clean, lightweight mobile device profile
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    
    try:
        # Paced random delays to look completely human
        time.sleep(random.uniform(4.5, 7.5))
        
        response = requests.get(url, headers=headers, timeout=15)
        html_text = response.text
        
        # Immediate verification if Amazon is hitting us with a block/captcha
        if response.status_code == 503 or "captcha" in html_text.lower() or "robot check" in html_text.lower():
            return "BLOCKED BY AMAZON", "None", "None", "None"
            
        soup = BeautifulSoup(html_text, 'html.parser')
        
        # 1. Broad Price Extraction (Searching everywhere on the mobile structure)
        price = "None"
        price_selectors = [
            "span.a-price-whole",
            "span.apexPriceToPay span.a-offscreen",
            "span.a-price .a-offscreen",
            ".a-size-large.a-color-price",
            "#price_inside_buybox",
            "span.a-color-price"
        ]
        
        for sel in price_selectors:
            element = soup.select_one(sel)
            if element:
                price = element.get_text().strip()
                break
        
        # Clean price text formatting safely
        if price != "None":
            price = re.sub(r'\s+', '', price)
            price_match = re.search(r'([£\$]\d+[\.,]\d\d|\d+[\.,]\d\d|[£\$]\d+)', price)
            if price_match:
                price = price_match.group(1)

        # 2. Refined Out of Stock Detection
        is_oos = any(kw in html_text.lower() for kw in ["currently unavailable", "temporary out of stock", "out of stock"])
        
        # Cross-verify: If there's an "Add to Cart" or "Buy Now" button, it IS in stock
        if "add to cart" in html_text.lower() or "add to basket" in html_text.lower() or "buy now" in html_text.lower():
            is_oos = False

        # 3. Seller Identification
        seller = "Third-Party"
        if "sold by amazon" in html_text.lower() or "dispatched from and sold by amazon" in html_text.lower():
            seller = "Amazon"
        elif "fulfilled by amazon" in html_text.lower() or "dispatched from amazon" in html_text.lower() or "ships from amazon" in html_text.lower():
            seller = "Third-Party (Prime)"
            
        # 4. Final Status Processing
        status = "IN STOCK"
        if is_oos:
            status = "OUT OF STOCK"
            price = "None"
        else:
            low_stock_match = re.search(r'only\s+(\d+)\s+left\s+in\s+stock', html_text.lower())
            if low_stock_match:
                status = f"LOW IN STOCK ({low_stock_match.group(1)} Left)"
                
        # If price is still missing but we know it's in stock, mark it clearly
        if status == "IN STOCK" and price == "None":
            status = "IN STOCK (Price Hidden)"

        return status, price, seller, "None"

    except Exception as e:
        return "ERROR", "None", "None", "None"

if uploaded_file is not None:
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
        
    st.write("### Preview of Uploaded Data:")
    st.dataframe(df.head())
    
    columns = df.columns.tolist()
    
    default_sku = columns[0]
    default_url = columns[0]
    for col in columns:
        if "sku" in col.lower() or "id" in col.lower():
            default_sku = col
        if "url" in col.lower() or "link" in col.lower() or "amazon" in col.lower():
            default_url = col

    sku_col = st.selectbox("Select SKU Column", columns, index=columns.index(default_sku))
    url_col = st.selectbox("Select Amazon URL Column", columns, index=columns.index(default_url))
    
    if st.button("🚀 Start Tracking Prices & Stock"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        total_rows = len(df)
        
        for index, row in df.iterrows():
            sku = str(row[sku_col])
            url = str(row[url_col])
            
            status_text.text(f"Processing ({index+1}/{total_rows}): Checking SKU {sku}...")
            
            if pd.isna(row[url_col]) or "amazon" not in url.lower():
                results.append({"SKU": sku, "URL": url, "Live Price": "None", "Seller": "None", "Status": "INVALID URL"})
            else:
                status, price, seller, _ = parse_amazon_page(url)
                results.append({
                    "SKU": sku,
                    "URL": url,
                    "Live Price": price,
                    "Seller": seller,
                    "Status": status
                })
                
            progress_bar.progress((index + 1) / total_rows)
            
        status_text.text("✅ Finished checking all products!")
        
        result_df = pd.DataFrame(results)
        st.write("### Live Tracking Results:")
        st.dataframe(result_df)
        
        csv = result_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Updated Data as CSV", csv, "updated_prices.csv", "text/csv")
