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

# File Uploader
uploaded_file = st.file_uploader("Choose a file (Excel or CSV)", type=["xlsx", "csv"])

def parse_amazon_page(url):
    # Dynamic headers based on domain
    is_uk = "amazon.co.uk" in url.lower()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-GB,en;q=0.9" if is_uk else "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Device-Memory": "8"
    }
    
    try:
        # Paced human delay
        time.sleep(random.uniform(3.5, 6.5))
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 503 or "api-services-support@amazon" in response.text or "captcha" in response.text.lower():
            return "BLOCKED", "None", "None", "None"
            
        soup = BeautifulSoup(response.text, 'html.parser')
        html_text = response.text
        
        # 1. Check Out of Stock
        is_oos = any(kw in html_text.lower() for kw in ["currently unavailable", "temporary out of stock", "out of stock"])
        
        # 2. Extract Buy Box Price
        price = "None"
        price_selectors = [
            "span.a-price-whole",
            "span.apexPriceToPay span.a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_saleprice",
            ".a-price .a-offscreen"
        ]
        
        for sel in price_selectors:
            element = soup.select_one(sel)
            if element:
                price = element.get_text().strip()
                # Clean up duplicate symbols if any
                if price.count('£') > 1 or price.count('$') > 1:
                    price = price.split()[0]
                break
        
        # Clean price string from messy HTML spacing
        price = re.sub(r'\s+', '', price)
                
        # 3. Identify Seller
        seller = "Third-Party"
        merchant_text = soup.select_one("#merchantInfoID, #sellerProfileTriggerId")
        
        if "sold by amazon" in html_text.lower() or "dispatched from and sold by amazon" in html_text.lower():
            seller = "Amazon"
        elif merchant_text and ("amazon" in merchant_text.get_text().lower()):
            seller = "Amazon"
        elif "fulfilled by amazon" in html_text.lower() or "dispatched from amazon" in html_text.lower() or "ships from amazon" in html_text.lower():
            seller = "Third-Party (Prime)"
            
        # 4. Check Stock Status
        status = "IN STOCK"
        if is_oos:
            status = "OUT OF STOCK"
            price = "None"
        else:
            low_stock_match = re.search(r'only\s+(\d+)\s+left\s+in\s+stock', html_text.lower())
            if low_stock_match:
                status = f"LOW IN STOCK ({low_stock_match.group(1)} Left)"
                
        # 5. Extract Fallback Lowest 3rd Party Price
        fallback_price = "None"
        fallback_selectors = ["div#olpLinkWidget_feature_div span.a-color-price", "span.olp-new-link span.a-color-price", ".olp-links .a-color-price"]
        for f_sel in fallback_selectors:
            f_element = soup.select_one(f_sel)
            if f_element:
                fallback_price = f_element.get_text().strip()
                break
            
        return status, price, seller, fallback_price

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
    
    # Try to auto-select columns if common names exist
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
        
        result_df = pd.DataFrame(results)
        st.write("### Live Tracking Results:")
        st.dataframe(result_df)
        
        csv = result_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Updated Data as CSV", csv, "updated_prices.csv", "text/csv")
