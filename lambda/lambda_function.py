#!/usr/bin/env python3
"""
Stock Picker from streak_tech_analysis

This script gets stock analysis data from the streak_tech_analysis API endpoint
and picks the stocks for you to invest in based on the preset portifolio and risk
parameters. It updates the picks to a google sheet as well as sends it via email.

I have set this up as a lambda in AWS so that I get automated results every day.

Usage:
    python lambda_function.py

Dependencies:
    pip install aiohttp asyncio gspread_dataframe pandas requests

Author: Merlin Mary John with AI Assistant
Date: October 2, 2025
"""


import aiohttp
import asyncio
import gspread_dataframe as gd
import gspread.auth as gs
import json
import os
import pandas as pd
import requests
import smtplib

from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo


execution_time = datetime.now(tz=ZoneInfo('Asia/Kolkata')).strftime("%b-%d-%Y %H:%M")
portfolio_capital = 100000

risk_parameters = {
    "max_drawdown_percent": 5,
    "per_trade_loss_percent": 1,
    "daily_loss_percent": 2,
    "monthly_loss_percent": 4,
    "trading_horizon_days": 14
}

streak_url = f"https://technicalwidget.streak.tech/api/streak_tech_analysis/?timeFrame=hour&stock="


def get_stocks_list():
    symbols = set()
    pg = 1
    screeners_url = f"https://s-op.streak.tech/screeners/discover?pageNumber="

    while True:
        response = requests.get(f"{screeners_url}{pg}").json()
        data = response.get("data", {})
        results = data.get("results", [])
        
        for res in results:
            inner_results = res.get("results")
            if inner_results:
                for item in inner_results:
                    symbols.add(item.get("seg_sym"))
        
        total_pages = data.get("total_pages", 0)
        if pg >= total_pages:
            break
        pg += 1

    return symbols


def trading_script_with_position_sizing(api_data, risk_params, portfolio_value):
    """Given API data, risk params, and portfolio size, decide trade, prices, GTT, and position size."""
    def normalize_rsi(val): return val / 100
    def normalize_adx(val): return min(val / 40, 1)
    def normalize_willr(val): return (0 - val) / 100
    def normalize_macd(val): return min(max(val / 1000, 0), 1)

    weights = {
        "adx": 0.15,
        "rsi": 0.15,
        "macd": 0.15,
        "mac_long_term": 0.1,
        "mac_short_term": 0.1,
        "willR": 0.1,
        "stochastic_k": 0.1,
        "change": 0.1,
        "rec_macd": 0.05
    }

    if not isinstance(api_data, dict):
        print(type(api_data))
        print(api_data)

    adx_score = normalize_adx(api_data.get("adx", 0))
    rsi_score = normalize_rsi(api_data.get("rsi", 0))
    macd_score = normalize_macd(api_data.get("macd", 0))
    mac_long_term_score = 1 if api_data.get("mac_long_term", 0) > 0 else 0
    mac_short_term_score = 1 if api_data.get("mac_short_term", 0) > 0 else 0
    willr_score = normalize_willr(api_data.get("willR", -100))
    stochastic_k_score = api_data.get("stochastic_k", 0) / 100
    change_score = 1 if api_data.get("change", 0) > 0 else 0
    rec_macd_score = api_data.get("rec_macd", 0)

    weighted_score = (adx_score * weights["adx"] +
                      rsi_score * weights["rsi"] +
                      macd_score * weights["macd"] +
                      mac_long_term_score * weights["mac_long_term"] +
                      mac_short_term_score * weights["mac_short_term"] +
                      willr_score * weights["willR"] +
                      stochastic_k_score * weights["stochastic_k"] +
                      change_score * weights["change"] +
                      rec_macd_score * weights["rec_macd"])

    decision = {
        "symbol": api_data.get("symbol"),
        "segment": api_data.get("segment"),
        "weighted_score": round(weighted_score, 4)
    }
    threshold = 0.6

    if weighted_score >= threshold:
        decision["enter"] = True
        buy_price = api_data.get("close", 0)
        decision["buy_price"] = round(buy_price, 2)

        stop_loss_percent = 2  # Stop loss 2% below buy_price
        stop_loss_price = buy_price * (1 - stop_loss_percent / 100)
        target_price = buy_price * (1 + 4 / 100)  # Target 4% above buy_price
        decision["stop_loss_price"] = round(stop_loss_price, 2)
        decision["target_price"] = round(target_price, 2)

        decision["GTT"] = {
            "stop_loss_trigger": stop_loss_price,
            "target_trigger": target_price
        }

        # Position sizing: max shares to buy, respecting your risk
        max_per_trade_risk = portfolio_value * risk_params["per_trade_loss_percent"] / 100
        risk_per_share = buy_price - stop_loss_price
        max_shares = (max_per_trade_risk / risk_per_share) if risk_per_share != 0 else 0
        decision["max_shares"] = int(max_shares)
    else:
        decision["enter"] = False
        decision["reason"] = "Weighted score below threshold, no entry."

    return decision


async def fetch(session, seg_sym):
    try:
        async with session.get(f"{streak_url}{seg_sym}") as response:
            response.raise_for_status()
            json_response = await response.json()

            seg = seg_sym.split(":")
            json_response["segment"] = seg[0]
            json_response["symbol"] = seg[1]

            return json_response
    except Exception as e:
        return f"Error: {e}"


async def get_data(symbols):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, row) for row in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results


def send_email(df):
    # Email parameters
    sender_email = os.getenv("sender_email")
    receiver_email = os.getenv("receiver_email")
    subject = f"Trading Picks - {execution_time}"
    body = "Here are today's pick for your trade. Check the attachment"

    # Create EmailMessage object
    msg = EmailMessage()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.set_content(body)

    csv_content = df.to_csv(index=False).encode('utf-8')
    msg.add_attachment(
        csv_content,
        maintype='text',
        subtype='csv',
        filename=f'trading-picks-{execution_time}.csv'
    )

    # Send email via SMTP (example with Gmail SMTP)
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = os.getenv("sender_email")
    smtp_password = os.getenv("smtp_password")

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)

    print("Email sent successfully.")


def export_to_sheets(df, worksheet_name, folder_id=None, mode='r'):
    gspread_oauth = json.loads(os.getenv("gspread_oauth"))
    gc = gs.service_account_from_dict(gspread_oauth)
    ws = gc.open(
        "Trading Picks History",
        folder_id=folder_id
    ).worksheet(worksheet_name)

    max_rows = len(ws.get_all_values(major_dimension='rows'))
    if max_rows <= 1 and mode == 'a':
        mode = 'w'

    if(mode == 'w'):
        ws.clear()
        gd.set_with_dataframe(
            worksheet=ws,
            dataframe=df,
            include_index=False,
            include_column_header=True,
            resize=True
        )
        return True

    elif(mode == 'a'):
        ws.add_rows(df.shape[0])
        gd.set_with_dataframe(
            worksheet=ws,
            dataframe=df,
            include_index=False,
            include_column_header=False,
            row=max_rows + 1,
            resize=False
        )
        return True

    else:
        return gd.get_as_dataframe(worksheet=ws)
    

def lambda_handler(event, context):
    symbols = get_stocks_list()
    print(f"Total stocks: {len(symbols)}")

    results = asyncio.run(get_data(symbols))
    trade_decisions = [
        trading_script_with_position_sizing(
            data, risk_parameters, portfolio_capital
        ) for data in results if isinstance(data, dict)
    ]

    picks = pd.DataFrame(trade_decisions)
    picks = picks.loc[picks['enter']==True]
    picks = picks.sort_values(
        by=['weighted_score', 'buy_price'],
        ascending=[False, False]
    )
    picks["date_time"] = execution_time
    print(f"Total picks: {len(picks)}")

    worksheet = os.getenv("worksheet", "Picks")
    worksheet_folder = os.getenv("worksheet_folder")
    export_to_sheets(picks, worksheet, worksheet_folder, 'a')
    # send_email(picks)


if __name__ == "__main__":
    lambda_handler({}, {})
