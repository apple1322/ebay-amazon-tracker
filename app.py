import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import random
import re

st.set_page_config(page_title="EBay-Amazon Tracker", layout="wide")

st.title("📦 eBay-Amazon Price & Stock Monitor")
st.write("Upload your Excel/CSV file containing SKUs and Amazon UK URLs.")

# File Uploader
uploaded_file = st.file_uploader("Choose a file (Excel or CSV)", type=["xlsx", "csv"])

def parse_amazon_page(url):
    # Fake user agent to look like a normal browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-GB,en;q=0.9"
    }
    
    try:
        # 3 to 6 seconds random human-like delay
        time.sleep(random.uniform(3.0, 6.0))
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 503 or "api-services-support@amazon" in response.text:
            return "BLOCKED", "None", "None", "None"
            
        soup = BeautifulSoup(response.text, 'html.parser')
        html_text = response.text
        
        # 1. Check Out of Stock
        oos_keywords = ["currently unavailable", "out of stock", "dispatched from and sold by amazon"]
        is_oos = any(kw in html_text.lower() for kw in ["currently unavailable", "temporary out of stock"])
        
        # 2. Extract Buy Box Price & Seller
        price = "None"
        seller = "Third-Party"
        
        price_selectors = [
            "span.a-price-whole", 
            "#priceblock_ourprice", 
            "#priceblock_saleprice",
            "span.apexPriceToPay span.a-offscreen"
        ]
        
        for sel in price_selectors:
            element = soup.select_one(sel)
            if element:
                price = element.get_text().strip()
                break
                
        if "dispatched from and sold by amazon" in html_text.lower():
            seller = "Amazon"
        elif "fulfilled by amazon" in html_text.lower() or "dispatched from amazon" in html_text.lower():
            seller = "Third-Party (Prime)"
            
        # 3. Check Low Stock
        status = "IN STOCK"
        if is_oos:
            status = "OUT OF STOCK"
            price = "None"
        else:
            low_stock_match = re.search(r'only\s+(\d+)\s+left\s+in\s+stock', html_text.lower())
            if low_stock_match:
                status = f"LOW IN STOCK ({low_stock_match.group(1)} Left)"
                
        # 4. Extract Fallback Lowest 3rd Party Price
        fallback_price = "None"
        fallback_element = soup.select_one("div#olpLinkWidget_feature_div span.a-color-price")
        if fallback_element:
            fallback_price = fallback_element.get_text().strip()
            
        return status, price, seller, fallback_price

except Exception as e:
    return "ERROR", "None", "None", "None"

if uploaded_file is not None:
    # Read file safely
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
        
    st.write("### Preview of Uploaded Data:")
    st.dataframe(df.head())
    
    # Dynamically find column names
    columns = df.columns.tolist()
    sku_col = st.selectbox("Select SKU Column", columns)
    url_col = st.selectbox("Select Amazon URL Column", columns)
    
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
                results.append({"SKU": sku, "URL": url, "Live Price": "None", "Seller": "None", "Fallback 3rd Party": "None", "Status": "INVALID URL"})
            else:
                status, price, seller, fallback_price = parse_amazon_page(url)
                results.append({
                    "SKU": sku,
                    "URL": url,
                    "Live Price": price,
                    "Seller": seller,
                    "Fallback 3rd Party": fallback_price,
                    "Status": status
                })
                
            progress_bar.progress((index + 1) / total_rows)
            
        status_text.text("✅ Finished checking all products!")
        
        # Display Final Results
        result_df = pd.DataFrame(results)
        st.write("### Live Tracking Results:")
        st.dataframe(result_df)
        
        # Download Button for Updated Excel
        csv = result_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Updated Data as CSV", csv, "updated_prices.csv", "text/csv")
