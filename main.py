import discord
import random
import string
import json
import asyncio
import os
import qrcode
import configparser
import io
import psutil
import datetime
from discord.ext import commands
from utils import *
import chat_exporter  # Import the chat-exporter module
import platform


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

show_buyer_seller = config.getboolean('DisplaySettings', 'show_buyer_seller')

start_time = datetime.datetime.now()

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

@client.event
async def on_ready():
    client.add_view(PersistentCreateTicket())
    print(f'Logged in as {client.user}!')
    await tree.sync()

@tree.command(name='ticket-panel', description='Displays the ticket panel embed')
async def ticket_panel(interaction: discord.Interaction):
    await interaction.response.defer()
    member = interaction.user 
    guild = interaction.guild
    required_role = discord.utils.get(guild.roles, id=admin_role_id)
    
    if required_role not in member.roles:
        return

    embed = discord.Embed(
        title="Soapsfrw Auto MM",
        description="<a:purpleheart:1335653412603428935> Safe & Easy\n<a:purpleheart:1335653412603428935> No Fees\n<a:purpleheart:1335653412603428935> Available 24/7\n<a:purpleheart:1335653412603428935> Supports LTC only",
        color=embed_color
    )
    embed.set_footer(text=footer_text, icon_url=icon_url)  
    embed.set_thumbnail(url=thumbnail_url)

    view = PersistentCreateTicket()
    
    await interaction.channel.send(embed=embed, view=view)


class PersistentCreateTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.grey, custom_id="CreateTicket")
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = UserIdModal()
        await interaction.response.send_modal(modal)

class UserIdModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="User ID Input")
        self.user_id = discord.ui.TextInput(label="Enter the User ID of another user", required=True)
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        user_id = self.user_id.value

        user = interaction.guild.get_member(int(user_id))
        if user is None:
            await interaction.followup.send("That user is not in this server.", ephemeral=True)
            return

        deal_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))

        category = interaction.guild.get_channel(category_id)

        if category is None or not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send("Invalid category ID.", ephemeral=True)
            return

        new_channel = await interaction.guild.create_text_channel(
            name=f"mm-{interaction.user.name}",
            category=category
        )

        # Set permissions for the new channel
        await new_channel.set_permissions(interaction.guild.default_role, read_messages=False)  # Remove view permissions from @everyone
        await new_channel.set_permissions(interaction.user, read_messages=True, send_messages=True)  # Allow creator to view and send messages
        await new_channel.set_permissions(user, read_messages=True, send_messages=True)  # Allow the other user to view and send messages

        # Update the channel topic with the deal ID
        await new_channel.edit(topic=f"{deal_id}")

        deal_info = {
            "deal_id": deal_id,
            "channel_id": new_channel.id,
            "buyer": None,
            "seller": None,
            "deal_amount_usd": None,
            "amount_in_ltc": None,
            "timestamp": interaction.created_at.isoformat(),
        }

        data = load_data()
        data[deal_id] = deal_info
        save_data(data)

        embed = discord.Embed(
            title="SOAPSFRW AUTO MM",
            description=f"||Deal ID: {deal_id}||\n\nTo start, identify the buyer & seller by selecting the appropriate buttons below. Press the Next button to proceed.",
            color=embed_color
        )

        embed.set_footer(text=footer_text, icon_url=icon_url)  
        embed.set_thumbnail(url=thumbnail_url)
        await new_channel.send(embed=embed)


        embed = discord.Embed(
            title="Choose Your Role",
            color=embed_color
        )

        embed.add_field(name="Seller Role", value=f"None", inline=True)
        embed.add_field(name="Buyer Role", value=f"None")
        embed.set_footer(text=footer_text, icon_url=icon_url)  
        embed.set_thumbnail(url=thumbnail_url)
        view = RoleSelectorView(creator=interaction.user, other_user=user)

        await new_channel.send(embed=embed, view=view)


        await interaction.followup.send(f"- **Middleman Ticket Created: {new_channel.mention}**", ephemeral=True)

class RoleSelectorView(discord.ui.View):
    def __init__(self, creator: discord.Member, other_user: discord.Member):
        super().__init__(timeout=None)
        self.creator = creator
        self.other_user = other_user
        self.buyer = None
        self.seller = None

    async def get_deal_id(self, interaction: discord.Interaction):
        # Extract the deal ID from the channel topic
        return interaction.channel.topic

    def save_to_json(self, deal_id: str, buyer_id: int, seller_id: int):
        # Define the file path to the Data.json inside the Database folder
        file_path = 'Database/Data.json'

        # Load the JSON file
        with open(file_path, 'r') as f:
            data = json.load(f)

        # Update the buyer and seller information in the deal entry
        if deal_id in data:
            data[deal_id]['buyer'] = buyer_id
            data[deal_id]['seller'] = seller_id

        # Save the updated data back to the file
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)

    @discord.ui.button(label="Seller", style=discord.ButtonStyle.gray)
    async def seller_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.buyer and interaction.user.id == self.buyer.id:
            await interaction.response.send_message("You cannot select yourself as both buyer and seller.", ephemeral=True)
            return

        self.seller = interaction.user
        self.buyer = self.other_user if interaction.user == self.creator else self.creator

        await self.update_roles(interaction)

    @discord.ui.button(label="Buyer", style=discord.ButtonStyle.gray)
    async def buyer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.seller and interaction.user.id == self.seller.id:
            await interaction.response.send_message("You cannot select yourself as both buyer and seller.", ephemeral=True)
            return

        self.buyer = interaction.user
        self.seller = self.other_user if interaction.user == self.creator else self.creator

        await self.update_roles(interaction)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.buyer or not self.seller:
            await interaction.response.send_message("Both buyer and seller need to be selected before confirming.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        deal_id = await self.get_deal_id(interaction)
        self.save_to_json(deal_id, self.buyer.id, self.seller.id)

        await interaction.followup.send("Roles confirmed!", ephemeral=True)

        embed = discord.Embed(
            title="Amount of Deal",
            description=f"{self.seller.mention}, please enter the amount of the deal in USD.",
            color=0xffff00
        )
        await interaction.channel.send(embed=embed)

        def check(m):
            return m.author == self.seller and m.channel == interaction.channel

        while True:
            try:
                message = await interaction.client.wait_for('message', check=check, timeout=120)
                amount = float(message.content)
                confirmation_embed = discord.Embed(
                    title="Deal Amount Confirmation",
                    description=f"- Amount : **${amount:.2f} USD**\n\n- Accept or Reject the deal.",
                    color=embed_color
                )
                confirmation_embed.set_footer(text=footer_text, icon_url=icon_url)  
                confirmation_embed.set_thumbnail(url=thumbnail_url)
                view = DealConfirmationView(self.buyer, self.seller, amount)
                await interaction.channel.send(f"{self.buyer.mention}", embed=confirmation_embed, view=view)

                # Wait for the buyer's decision
                await view.wait()

                if view.confirmed:
                    break  # Deal is accepted, proceed with the next step

            except ValueError:
                await interaction.channel.send(f"{self.seller.mention}, please enter a valid number for the deal amount (e.g., 100.00).")
            except asyncio.TimeoutError:
                await interaction.channel.send(f"{self.seller.mention}, you took too long to respond. Please try again later.")
                break

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        # Send embed about the cancellation
        embed = discord.Embed(
            title="Transaction Cancelled",
            description="This transaction has been cancelled. The channel will be deleted in 15 seconds.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

        # Wait 15 seconds and delete the channel
        await asyncio.sleep(15)
        await interaction.channel.delete()

    async def update_roles(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        embed.clear_fields()

        seller_mention = self.seller.mention if self.seller else "None"
        buyer_mention = self.buyer.mention if self.buyer else "None"

        embed.add_field(name="Seller Role", value=seller_mention, inline=False)
        embed.add_field(name="Buyer Role", value=buyer_mention, inline=False)

        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(f"Roles updated:\nBuyer: {buyer_mention}\nSeller: {seller_mention}", ephemeral=True)


class DealConfirmationView(discord.ui.View):
    def __init__(self, buyer, seller, amount):
        super().__init__(timeout=None)
        self.buyer = buyer
        self.seller = seller
        self.amount = amount
        self.dealid = None
        self.confirmed = False  
        self.ltc_wallet_address = None
        self.payment_channel = None
        self.pending_sent = False 
        self.pending_detected = False 

    async def check_balance(self, ltc_wallet_address2):
        max_checks = 50
        check_count = 0

        while check_count < max_checks or self.pending_detected: 
            balance_data = get_ltc_balance(ltc_wallet_address2)
            
            if balance_data:
                incoming = float(balance_data["incoming"])
                incoming_pending = float(balance_data["incomingPending"])

                ltc_to_usd = get_ltc_to_usd_exchange_rate()

                if incoming_pending > 0 and not self.pending_detected:
                    pending_amount_usd = incoming_pending * ltc_to_usd
                    pending_embed = discord.Embed(
                        title="Pending Payment Detected",
                        description=(
                            f"> A Pending Transaction Is Detected.\n\n"
                            f"- ${pending_amount_usd:.2f} USD ({incoming_pending:.4f} LTC)"
                        ),
                        color=embed_color
                    )
                    pending_embed.set_footer(text=f"{footer_text} • Awaiting confirmation", icon_url=icon_url)
                    pending_embed.set_thumbnail(url=loading_url)

                    await self.payment_channel.send(embed=pending_embed)
                    self.pending_detected = True
                    self.pending_sent = True

                if self.pending_detected and incoming_pending == 0 and incoming > 0:
                    confirmed_amount_usd = incoming * ltc_to_usd
                    confirmed_embed = discord.Embed(
                        title="Payment Received",
                        description=(
                            f"> The Pending Transaction Is Now Confirmed.\n\n"
                            f"- **{confirmed_amount_usd:.2f} USD ({incoming:.4f} LTC)**\n\n"
                        ),
                        color=0x00FF00
                    )

                    view = PaymentActionView(buyer=self.buyer, seller=self.seller, amount=incoming)

                    confirmed_embed.set_footer(text=f"{footer_text} • Payment Confirmed", icon_url=icon_url)
                    confirmed_embed.set_thumbnail(url=tick_image)

                    database_folder = "Database"
                    data_file = os.path.join(database_folder, "Data.json")

                    os.makedirs(database_folder, exist_ok=True)

                    if os.path.exists(data_file):
                        with open(data_file, 'r') as file:
                            data = json.load(file)
                    else:
                        data = {}

                    if self.dealid in data:
                            data[self.dealid]["received_amount_ltc"] = incoming
                            data[self.dealid]["received_amount_usd"] = confirmed_amount_usd

                    with open(data_file, 'w') as file:
                        json.dump(data, file, indent=4)

                    await self.payment_channel.send(embed=confirmed_embed, view=view)
                    break 

            if not self.pending_detected:
                check_count += 1

            await asyncio.sleep(15)

        if check_count >= max_checks and not self.pending_detected:
            timeout_embed = discord.Embed(
                title="Payment Not Detected",
                description="Payment was not detected after multiple checks. Closing the ticket.",
                color=discord.Color.red()
            )
            timeout_embed.set_footer(text=footer_text, icon_url=icon_url)
            timeout_embed.set_thumbnail(url=thumbnail_url)
            
            await self.payment_channel.send(embed=timeout_embed)



    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.buyer:
            await interaction.response.send_message("Only the buyer can accept the deal.", ephemeral=True)
            return
        self.payment_channel = interaction.channel
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        confirmation_embed = interaction.message.embeds[0]
        confirmation_embed.set_footer(text=f"Deal accepted by {self.buyer.display_name}")
        await interaction.message.edit(embed=confirmation_embed)

        ltc_wallet_address, private_key = create_new_ltc_address()  # Generate the new LTC address
        ltc_to_usd = get_ltc_to_usd_exchange_rate()  # Get the LTC to USD exchange rate
        ltc_amount = self.amount / ltc_to_usd  # Calculate the LTC amount

        store_deal_data(interaction.channel.topic, ltc_wallet_address, private_key, ltc_amount, self.amount)
        self.dealid = interaction.channel.topic
        payment_embed = discord.Embed(
            title="Waiting For Payment",
            description=(
                f"> Payment Credentials Are Given Below :\n\n"
                f"- **Address:** `{ltc_wallet_address}`\n"
                f"- **Amount to pay:** **{ltc_amount:.4f} LTC**\n\n"
                "> Your Payment Will Be Detected Automatically"
            ),
            color=embed_color
        )

        payment_embed.set_footer(text=footer_text, icon_url=icon_url)  
        payment_embed.set_thumbnail(url=ltc_image)

        view = PaymentEmbedView(ltc_wallet_address, ltc_amount)
        await interaction.channel.send(embed=payment_embed, view=view)
        
        asyncio.create_task(self.check_balance(ltc_wallet_address))

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.buyer:
            await interaction.response.send_message("Only the buyer can reject the deal.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        confirmation_embed = interaction.message.embeds[0]
        confirmation_embed.set_footer(text=f"Deal rejected by {self.buyer.display_name}")
        await interaction.message.edit(embed=confirmation_embed)


        embed = discord.Embed(
            title="Amount of Deal",
            description=f"{self.seller.mention}, please enter the amount of the deal in USD.",
            color=0xffff00
        )

        await interaction.channel.send(f"{self.seller.mention}", embed=embed)

        self.confirmed = False

        def check(m):
            return m.author == self.seller and m.channel == interaction.channel

        while True:
            try:
                message = await interaction.client.wait_for('message', check=check, timeout=120)
                amount = float(message.content)
                confirmation_embed = discord.Embed(
                    title="Deal Amount Confirmation",
                    description=f"- Amount : **${amount:.2f} USD**\n\n- Accept or Reject the deal.",
                    color=embed_color
                )
                confirmation_embed.set_footer(text=footer_text, icon_url=icon_url)  
                confirmation_embed.set_thumbnail(url=thumbnail_url)
                view = DealConfirmationView(self.buyer, self.seller, amount)
                await interaction.channel.send(f"{self.buyer.mention}",embed=confirmation_embed, view=view)

                # Wait for the buyer's decision
                await view.wait()

                if view.confirmed:
                    break  # Deal is accepted, proceed with the next step

            except ValueError:
                await interaction.channel.send(f"{self.seller.mention}, please enter a valid number for the deal amount (e.g., 100.00).")
            except asyncio.TimeoutError:
                await interaction.channel.send(f"{self.seller.mention}, you took too long to respond. Please try again later.")
                break


class PaymentEmbedView(discord.ui.View):
    def __init__(self, ltc_wallet_address: str, ltc_amount: float):
        super().__init__(timeout=None)
        self.ltc_wallet_address = ltc_wallet_address
        self.ltc_amount = ltc_amount

    @discord.ui.button(label="Copy Address", style=discord.ButtonStyle.primary)
    async def copy_address(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"{self.ltc_wallet_address}")
        await interaction.channel.send(f"{self.ltc_amount:.4f}")
        button.disabled = True  # Disable the button after clicking
        await interaction.message.edit(view=self)  # Update the message with disabled button

    @discord.ui.button(label="QR Code", style=discord.ButtonStyle.secondary)
    async def qr_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        qr_data = f"litecoin:{self.ltc_wallet_address}?amount={self.ltc_amount:.4f}"

        qr_image = qrcode.make(qr_data)

        buffer = io.BytesIO()
        qr_image.save(buffer, format='PNG')
        buffer.seek(0)

        qr_embed = discord.Embed(
            title="Scan to Pay",
            description="Scan the QR code below to pay with Litecoin.",
            color=embed_color
        )
        qr_embed.set_image(url="attachment://qr_code.png")

        await interaction.followup.send(embed=qr_embed, file=discord.File(fp=buffer, filename='qr_code.png'))
        button.disabled = True 
        await interaction.message.edit(view=self)







class PaymentActionView(discord.ui.View):
    def __init__(self, buyer, seller, amount):
        super().__init__(timeout=None)
        self.buyer = buyer
        self.seller = seller
        self.amount = amount

    @discord.ui.button(label="Release", style=discord.ButtonStyle.green)
    async def release_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.buyer:
            embed = discord.Embed(
                title="Unauthorized Action",
                description="> **Only the buyer can release the payment.**",
                color=0xFFFFFF
            )
            embed.set_footer(text=footer_text, icon_url=icon_url)
            embed.set_thumbnail(url=thumbnail_url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        confirm_view = ConfirmReleaseView(self.buyer,self.seller, self.amount)
        embed = discord.Embed(
            title="Release Payment Confirmation",
            description=(
                "> **Are you sure you want to release the payment?**\n\n"
                f"**Amount:** `{self.amount} USD`\n"
                "- Click the button below to confirm your action."
            ),
            color=0xFFFFFF
        )
        embed.set_footer(text=footer_text, icon_url=icon_url)
        embed.set_thumbnail(url=thumbnail_url)
        await interaction.response.send_message(embed=embed, view=confirm_view)

    @discord.ui.button(label="Refund", style=discord.ButtonStyle.red)
    async def refund_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.buyer:
            confirm_view = ConfirmRefundView(self.seller, self.buyer, self.amount, refund_initiator=self.buyer)
            embed = discord.Embed(
                title="Refund Requested by Buyer",
                description=(
                    f"> **Refund request initiated by** {self.buyer.mention}.\n\n"
                    f"**Waiting for** {self.seller.mention} **to confirm the refund.**"
                ),
                color=0xFFFFFF
            )
            embed.set_footer(text=footer_text, icon_url=icon_url)
            embed.set_thumbnail(url=thumbnail_url)
            await interaction.response.send_message(embed=embed, view=confirm_view)

        elif interaction.user == self.seller:
            confirm_view = ConfirmRefundView(self.seller, self.buyer, self.amount, refund_initiator=self.seller)
            embed = discord.Embed(
                title="Refund Requested by Seller",
                description=(
                    f"> **Refund request initiated by** {self.seller.mention}.\n\n"
                    f"**Waiting for** {self.buyer.mention} **to confirm the refund.**"
                ),
                color=0xFFFFFF
            )
            embed.set_footer(text=footer_text, icon_url=icon_url)
            embed.set_thumbnail(url=thumbnail_url)
            await interaction.response.send_message(embed=embed, view=confirm_view)

class ConfirmReleaseView(discord.ui.View):
    def __init__(self, buyer, seller, amount):
        super().__init__(timeout=None)
        self.buyer = buyer
        self.seller = seller
        self.amount = amount

    @discord.ui.button(label="Confirm Release", style=discord.ButtonStyle.green)
    async def confirm_release(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.buyer:
            embed = discord.Embed(
                title="Unauthorized Action",
                description="> **Only the buyer can confirm the release.**",
                color=embed_color
            )
            embed.set_footer(text=footer_text, icon_url=icon_url)
            embed.set_thumbnail(url=thumbnail_url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="Payment Released",
            description=(f"- 💸 **Payment Is Now Released :** `{self.amount} USD`\n\n- Please Provide Your Ltc Address."),
            color=embed_color
        )
        embed.set_footer(text=footer_text, icon_url=icon_url)
        embed.set_thumbnail(url=thumbnail_url)
        

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.channel.send(f"{self.seller.mention}", embed=embed)

        def check(m):
            return m.author == self.seller and m.channel == interaction.channel

        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=None)
            ltc_address = msg.content
            await interaction.channel.send(f"**> LTC ADDRESS :** `{ltc_address}`.")

            deal_id = interaction.channel.topic if interaction.channel.topic else "Unknown Deal ID"

            await send_ltc(ltc_address, self.amount, interaction, deal_id)


        except asyncio.TimeoutError:
            await interaction.channel.send(f"{self.seller.mention}, you did not provide an LTC address in time. Please try again.")

class ConfirmRefundView(discord.ui.View):
    def __init__(self, seller, buyer, amount, refund_initiator):
        super().__init__(timeout=None)
        self.seller = seller
        self.buyer = buyer
        self.amount = amount
        self.refund_initiator = refund_initiator

    @discord.ui.button(label="Confirm Refund", style=discord.ButtonStyle.red)
    async def confirm_refund(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (interaction.user == self.seller and self.refund_initiator == self.buyer) or (interaction.user == self.buyer and self.refund_initiator == self.seller):
            embed = discord.Embed(
                title="Refund Confirmed",
                description=(f"- 💸 **Payment Is Now Released :** `{self.amount} USD`\n\n- Please Provide Your Ltc Address."),
                color=embed_color
            )
            embed.set_footer(text=footer_text, icon_url=icon_url)
            embed.set_thumbnail(url=thumbnail_url)
            

            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)

            await interaction.channel.send(f"{self.buyer.mention}", embed=embed)

            def check(m):
                return m.author == self.buyer and m.channel == interaction.channel

            try:
                msg = await interaction.client.wait_for('message', check=check, timeout=None)
                ltc_address = msg.content
                await interaction.channel.send(f"**> LTC ADDRESS :** `{ltc_address}`.")

                # Get the deal ID from the channel's topic
                deal_id = interaction.channel.topic if interaction.channel.topic else "Unknown Deal ID"

                # Send LTC and get the transaction ID
                await send_ltc(ltc_address, self.amount, interaction, deal_id)

                

            except asyncio.TimeoutError:
                await interaction.channel.send(f"{self.buyer.mention}, you did not provide an LTC address in time. Please try again.")
        else:
            embed = discord.Embed(
                title="Unauthorized Action",
                description="> **You are not authorized to confirm this refund.**",
                color=embed_color
            )
            embed.set_footer(text=footer_text, icon_url=icon_url)
            embed.set_thumbnail(url=thumbnail_url)
            await interaction.response.send_message(embed=embed, ephemeral=True)




@tree.command(name="release", description="Release LTC to a specified address for a given deal")
async def release(interaction: discord.Interaction, deal_id: str, ltc_address: str, ltc_amount: float = None):
    await interaction.response.defer()
    interaction_channel = interaction
    guild = interaction.guild
    member = interaction.user  # The user who invoked the command
    
    # Check if the member has the required role
    required_role = discord.utils.get(guild.roles, id=admin_role_id)
    
    if required_role not in member.roles:
        await interaction_channel.send(f"❌ You do not have the required role to use this command.", ephemeral=True)
        return

    # Load the deal data from Database/Data.json
    try:
        with open('Database/Data.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:   
        await interaction_channel.channel.send("Database file not found.")
        return
    
    deal_data = data.get(deal_id)
    
    if not deal_data:
        await interaction_channel.channel.send(f"Deal ID `{deal_id}` not found.")
        return
    
    # Retrieve LTC amount from the deal if not provided
    if ltc_amount is None:
        ltc_amount = deal_data.get("received_amount_ltc")
        if ltc_amount is None:
            await interaction_channel.send(f"LTC amount not found for deal ID `{deal_id}`.")
            return
    
    # Call your `send_ltc` function here to process the transaction
    await send_ltc(ltc_address, ltc_amount, interaction_channel, deal_id)


@tree.command(name="transcript", description="Generate a transcript of this channel")
async def transcript(interaction: discord.Interaction):
    channel = interaction.channel

    # Notify the user that transcript generation has started
    await interaction.response.send_message("Generating transcript, please wait...")

    messages = []
    async for message in channel.history(limit=None):
        messages.append(message)

    # Now pass the messages to raw_export
    transcript = await chat_exporter.raw_export(channel, messages)

    if transcript is None:
        await interaction.channel.send("Unable to generate the transcript. Please try again.")
        return

    # Define the transcript file path
    file_name = f"{channel.name}-transcript.html"
    file_path = f"Database/Transcripts/{file_name}"

    # Create the folder if it doesn't exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Save the transcript to an HTML file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(transcript)

    # Send the transcript as a file to the user in the channel
    with open(file_path, "rb") as f:
        await interaction.channel.send(file=discord.File(f, file_name))




@tree.command(name="delete", description="Delete this channel (Admin Only)")
async def delete(interaction: discord.Interaction):
    admin_role = interaction.guild.get_role(admin_role_id)
    if admin_role not in interaction.user.roles:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if interaction.channel.category and interaction.channel.category.id == category_id:
        embed = discord.Embed(
            title="Channel Deletion",
            description="This channel will be deleted in **5 seconds**.",
            color=embed_color
        )
        
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Deleted by admin command.")
    else:
        await interaction.response.send_message("This channel cannot be deleted because it is not in the specified category.", ephemeral=True)



@tree.command(name="profile", description="Show user exchange profile")
async def profile(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user  # Default to the command invoker if no user is mentioned

    user_data_file = 'Database/User.json'
    
    try:
        with open(user_data_file, 'r') as f:
            user_data = json.load(f)
    except FileNotFoundError:
        user_data = {}

    user_info = user_data.get(str(user.id), None)

    if user_info is None:
        embed = discord.Embed(
            title="Profile Not Found",
            description=f"No exchange data found for {user.mention}.",
            color=embed_color
        )
        await interaction.response.send_message(embed=embed)
        return

    total_spent = user_info.get('total_spent', 0)
    total_earned = user_info.get('total_earned', 0)

    embed = discord.Embed(
        title=f"{user.name}'s Profile",
        color=embed_color
    )
    embed.add_field(name="Total Spent (USD)", value=f"${total_spent:.3f}", inline=False)
    embed.add_field(name="Total Earned (USD)", value=f"${total_earned:.3f}", inline=False)
    embed.set_thumbnail(url=user.avatar.url)  # User's avatar
    embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)

    await interaction.response.send_message(embed=embed)


@tree.command(name="about", description="Displays bot statistics and specs.")
async def about(interaction: discord.Interaction):
    uptime = datetime.datetime.now() - start_time
    total_seconds = int(uptime.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    cpu_usage = psutil.cpu_percent(interval=1)
    ram_usage = psutil.virtual_memory().percent
    ping = round(client.latency * 1000)  # Latency in milliseconds

    try:
        with open('Database/DealStats.json', 'r') as f:
            data = json.load(f)
            total_deals_completed = data.get("total_deals", 0)
            total_amount_deals = data.get("total_amount_usd", 0.0)
    except Exception as e:
        print(f"Error loading deal stats: {e}")
        total_deals_completed = 0
        total_amount_deals = 0.0

    embed = discord.Embed(
        title="Bot Statistics",
        description="Here are the current statistics and specifications of the bot.",
        color=embed_color
    )
    embed.add_field(name="Ping", value=f"{ping} ms", inline=True)
    embed.add_field(name="Uptime", value=f"{hours}h {minutes}m {seconds}s", inline=True)
    embed.add_field(name="CPU Usage", value=f"{cpu_usage}%", inline=True)
    embed.add_field(name="RAM Usage", value=f"{ram_usage}%", inline=True)
    embed.add_field(name="Developer Tag", value="@soapsfrw (921434922399453184)", inline=True)
    embed.add_field(name="Py Version", value=f"{platform.python_version()}", inline=True)
    
    embed.set_footer(text=footer_text, icon_url=icon_url)
    embed.set_thumbnail(url=thumbnail_url)

    await interaction.response.send_message(embed=embed)

    
@tree.command(name="statistics", description="Displays statistics about deals.")
async def statistics(interaction: discord.Interaction):
    try:
        with open('Database/DealStats.json', 'r') as f:
            data = json.load(f)
            total_deals_completed = data.get("total_deals", 0)
            total_amount_deals = data.get("total_amount_usd", 0.0)
    except Exception as e:
        print(f"Error loading deal stats: {e}")
        total_deals_completed = 0
        total_amount_deals = 0.0

    python_version = platform.python_version()
    developer_tag = "Developer: @soapsfrw"  # Replace with actual developer name

    embed = discord.Embed(
        title="Deal Statistics",
        description=(
            f"- Total Deals : **{total_deals_completed}**\n"
            f"- Total Amount : **${total_amount_deals:.2f}**"
        ),
        color=embed_color
    )

    embed.set_footer(text=footer_text, icon_url=icon_url)
    embed.set_thumbnail(url=thumbnail_url)

    await interaction.response.send_message(embed=embed)


    
client.run(config['Token']['TOKEN'], reconnect=True)
