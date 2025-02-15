import json
import os
import requests
import asyncio
import discord
import chat_exporter 
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

embed_color = int(config['EmbedSettings']['embed_color'], 16)
footer_text = config['EmbedSettings']['footer_text']
icon_url = config['EmbedSettings']['icon_url']
thumbnail_url = config['EmbedSettings']['thumbnail_url']
loading_url = config['EmbedSettings']['loading_url']
ltc_image = config['EmbedSettings']['ltc_image']
tick_image = config['EmbedSettings']['tick_image']

TATUM_APIKEY = config['APIKeys']['TATUM_APIKEY']

mm_log_channel_id = int(config['ChannelSettings']['mm_log_channel_id'])
category_id = int(config['ChannelSettings']['category_id'])

admin_role_id = int(config['RoleSettings']['admin_role_id'])
client_role_id = int(config['RoleSettings']['client_role_id'])


show_buyer_seller = config.getboolean('DisplaySettings', 'show_buyer_seller')


TATUM_BALANCE_URL = "https://api.tatum.io/v3/litecoin/address/balance/{address}"


def load_data():
    try:
        with open("Database/Data.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(data):
    with open("Database/Data.json", "w") as f:
        json.dump(data, f, indent=4)


def get_ltc_to_usd_exchange_rate():
    url = "https://api.coinbase.com/v2/exchange-rates?currency=LTC"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        ltc_to_usd = float(data['data']['rates']['USD'])
        return ltc_to_usd
    else:
        raise Exception(f"Failed to get exchange rate. Status code: {response.status_code}, Response: {response.text}")

def create_new_ltc_address():
    endpoint = "https://api.blockcypher.com/v1/ltc/main/addrs"
    response = requests.post(endpoint)

    if response.status_code == 201:
        data = response.json()
        new_address = data["address"]
        private_key = data["wif"]
        return new_address, private_key
    else:
        raise Exception("Error generating new LTC address.")

def store_deal_data(deal_id, ltc_address, private_key, ltc_amount, usd_amount):
    # Define the file path
    database_folder = "Database"
    data_file = os.path.join(database_folder, "Data.json")

    os.makedirs(database_folder, exist_ok=True)

    if os.path.exists(data_file):
        with open(data_file, 'r') as file:
            data = json.load(file)
    else:
        data = {}

    if deal_id in data:
            data[deal_id]["ltc_address"] = ltc_address
            data[deal_id]["private_key"] = private_key
            data[deal_id]["amount_in_ltc"] = ltc_amount
            data[deal_id]["deal_amount_usd"] = usd_amount

    with open(data_file, 'w') as file:
        json.dump(data, file, indent=4)




def get_ltc_balance(address):
    headers = {
        "x-api-key": TATUM_APIKEY
    }
    url = TATUM_BALANCE_URL.format(address=address)

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json() 
    else:
        return None




async def send_ltc(recipient_address, amount, interaction_channel, deal_id):
    with open('Database/Data.json', 'r') as f:
        data = json.load(f)

    deal_data = data.get(deal_id)
    
    if deal_data is None:
        await interaction_channel.channel.send("Deal ID not found.")
        return None

    private_key = deal_data.get("private_key")  # Sender's private key
    sender_address = deal_data.get("ltc_address")  # Sender's LTC address
    received_amount_ltc = deal_data.get("received_amount_ltc")  # Total amount received

    if amount <= 0:
        await interaction_channel.channel.send("Amount must be greater than 0.")
        return None

    fee = 0.00005  
    amount_after_fee = amount - fee
    amount_after_fee = round(amount_after_fee, 7)

    if amount_after_fee <= 0:
        await interaction_channel.channel.send("Amount after fee deduction must be greater than 0.")
        return None


    payload = {
        "fromAddress": [{
            "address": sender_address,
            "privateKey": private_key
        }],
        "to": [{
            "address": recipient_address,
            "value": float(amount_after_fee) 
        }],
        "fee": str(fee),  
        "changeAddress": sender_address
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": TATUM_APIKEY 
    }

    try:
        response = requests.post("https://api.tatum.io/v3/litecoin/transaction", json=payload, headers=headers)
        response.raise_for_status()  
        data = response.json()
        tx_id = data.get("txId")  

        embed = discord.Embed(
            title="Payment Sent",
            description="The Litecoin payment has been successfully sent.",
            color=embed_color
        )
        embed.add_field(name="Deal ID", value=deal_id, inline=True)
        embed.add_field(name="To Address", value=recipient_address, inline=True)
        embed.add_field(name="Amount Sent (LTC)", value=f"{amount_after_fee} LTC", inline=True)
        embed.add_field(name="Transaction ID", value=f"[{tx_id}](https://blockchair.com/litecoin/transaction/{tx_id})", inline=False)
       

        await interaction_channel.channel.send(embed=embed)
        await complete_deal(deal_id, interaction_channel)

    except requests.RequestException as e:
        if response is not None and response.status_code == 400:
            print(e)
        await interaction_channel.channel.send("Failed to send LTC. Please check the transaction details and try again.")
        return None


async def complete_deal(deal_id, interaction):
    
    interaction_channel = interaction.channel
    guild = interaction.guild
    with open('Database/Data.json', 'r') as f:
        data = json.load(f)

    deal_data = data.get(deal_id)
    
    if deal_data is None:
        await interaction_channel.send("Deal ID not found.")
        return None

    buyer_id = deal_data.get("buyer")
    seller_id = deal_data.get("seller")
    amount_usd = deal_data.get("received_amount_usd")
    received_amount_ltc = deal_data.get("received_amount_ltc")

    if not buyer_id or not seller_id:
        await interaction_channel.send("Incomplete deal data.")
        return None

    buyer = guild.get_member(buyer_id)
    seller = guild.get_member(seller_id)

    if not buyer or not seller:
        await interaction_channel.send("Could not find buyer or seller in the guild.")
        return None

    client_role = guild.get_role(client_role_id)

    if client_role:
        await buyer.add_roles(client_role)
        await seller.add_roles(client_role)

    user_file = 'Database/User.json'
    try:
        with open(user_file, 'r') as f:
            user_data = json.load(f)
    except FileNotFoundError:
        user_data = {}

    if str(buyer_id) in user_data:
        user_data[str(buyer_id)]['total_spent'] += amount_usd
    else:
        user_data[str(buyer_id)] = {
            'username': str(buyer),
            'total_spent': amount_usd,
            'total_earned': 0
        }

    if str(seller_id) in user_data:
        user_data[str(seller_id)]['total_earned'] += amount_usd
    else:
        user_data[str(seller_id)] = {
            'username': str(seller),
            'total_spent': 0,
            'total_earned': amount_usd
        }

    with open(user_file, 'w') as f:
        json.dump(user_data, f, indent=4)


    transcript_file_path = f'Database/Transcripts/{deal_id}.html'

    # Export chat from the channel and save it as an HTML file
    transcript = await chat_exporter.export(interaction_channel)
    if transcript is None:
        await interaction_channel.send("Failed to generate the transcript.")
        return

    with open(transcript_file_path, 'w', encoding='utf-8') as f:
        f.write(transcript)


    embed = discord.Embed(
        title="Deal Completed",
        description=f"The deal with ID `{deal_id}` has been successfully completed.",
        color=embed_color
    )
    embed.add_field(name="Deal ID", value=deal_id, inline=True)
    embed.add_field(name="Amount (USD)", value=f"${amount_usd}", inline=True)
    embed.add_field(name="Amount (LTC)", value=f"{received_amount_ltc} LTC", inline=True)
    embed.add_field(name="Buyer", value=buyer.mention, inline=True)
    embed.add_field(name="Seller", value=seller.mention, inline=True)

    try:
        await buyer.send(embed=embed, file=discord.File(transcript_file_path))
        await seller.send(embed=embed, file=discord.File(transcript_file_path))
    except discord.Forbidden:
        await interaction_channel.send("Failed to send DM to buyer or seller.")

    await interaction_channel.send(embed=embed)

    mm_embed = discord.Embed(
        title="MM Deal Log",
        description=f"Deal `{deal_id}` has been completed.",
        color=embed_color
    )
    mm_embed.add_field(name="Deal ID", value=deal_id, inline=True)
    mm_embed.add_field(name="Amount (USD)", value=f"${amount_usd}", inline=True)
    mm_embed.add_field(name="Amount (LTC)", value=f"{received_amount_ltc} LTC", inline=True)

    if show_buyer_seller:
        mm_embed.add_field(name="Buyer", value=buyer.mention, inline=True)
        mm_embed.add_field(name="Seller", value=seller.mention, inline=True)
    else:
        mm_embed.add_field(name="Buyer", value="Anonymous", inline=True)
        mm_embed.add_field(name="Seller", value="Anonymous", inline=True)

    mm_log_channel = guild.get_channel(mm_log_channel_id)
    if mm_log_channel:
        await mm_log_channel.send(embed=mm_embed)

    stats_file = 'Database/DealStats.json'
    try:
        with open(stats_file, 'r') as f:
            deal_stats = json.load(f)
    except FileNotFoundError:
        deal_stats = {"total_deals": 0, "total_amount_usd": 0.0}

    deal_stats["total_deals"] += 1
    deal_stats["total_amount_usd"] += amount_usd

    with open(stats_file, 'w') as f:
        json.dump(deal_stats, f, indent=4)

    new_channel_name = f"closed-{deal_id}"
    await interaction_channel.edit(name=new_channel_name)
