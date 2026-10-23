import os
import re
import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands


TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

APPLICATION_BANNER_URL = (
    "https://i.pinimg.com/736x/43/4f/65/434f65e5776197e3e48a37eaeeecc45e.jpg"
)

STAFF_ROLES = {
    1388962793042214942,
    910407932200513556,
    1368922573315768332,
    1374223820453580800,
    910405176752492545,
    910406452114493442,
    1511689439959847043,
    1469029533876224142,
    1401988464144023676,
}

APPLICATION_CATEGORY_ID = 1365588391810564228
RESULTS_CHANNEL_ID = 1505995665069703178
PORTFOLIO_CATEGORY_ID = 1557947722680504472

PORTFOLIO_THREADS = [
    "📋・рп-отчёты",
    "⚔️・арена",
    "🎥・откаты-с-компетитив",
    "💬・чат",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("family-bot")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

COLOR = discord.Color.from_rgb(19, 20, 27)
ACCENT = discord.Color.from_rgb(119, 93, 255)


def is_staff(member):
    return isinstance(member, discord.Member) and any(
        role.id in STAFF_ROLES for role in member.roles
    )


def get_channel(guild, channel_id, channel_type=None):
    channel = guild.get_channel(channel_id) if guild else None
    if channel_type is None or isinstance(channel, channel_type):
        return channel
    return None


async def deny(interaction, message="У вас недостаточно прав."):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        log.debug("Не удалось отправить ответ на interaction", exc_info=True)


def safe_name(value, limit=80):
    value = re.sub(
        r"[^a-zа-яё0-9_-]+",
        "-",
        value.lower().strip(),
        flags=re.I,
    )
    return re.sub(r"-+", "-", value).strip("-")[:limit] or "user"


def get_applicant_id(channel):
    if not channel or not channel.topic:
        return None
    match = re.search(r"APPLICATION_OWNER:(\d+)", channel.topic)
    return int(match.group(1)) if match else None


def get_portfolio_categories(guild):
    original = get_channel(guild, PORTFOLIO_CATEGORY_ID, discord.CategoryChannel)
    if not original:
        return []
    return [category for category in guild.categories if category.name == original.name]


async def get_portfolio_category(guild):
    original = get_channel(guild, PORTFOLIO_CATEGORY_ID, discord.CategoryChannel)
    if not original:
        raise ValueError("Исходная категория портфелей не найдена.")

    categories = get_portfolio_categories(guild)
    for category in categories:
        if len(category.channels) < 50:
            return category

    return await guild.create_category(
        name=original.name,
        overwrites=original.overwrites,
        position=original.position,
        reason="Автоматическое создание дополнительной категории портфелей",
    )


def panel_embed():
    embed = discord.Embed(
        title="Заявка на вступление в семью",
        description=(
            "**Заполни анкету и дождись решения рекрута.**\n\n"
            "**Статус набора:** `● Открыт`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "**Перед подачей заявки**\n"
            "• Указывай достоверную информацию.\n"
            "• Проверь правильность заполнения всех полей.\n"
            "• Укажи предыдущий игровой опыт и семьи.\n\n"
            "**После отправки**\n"
            "• Рекрут рассмотрит твою анкету.\n"
            "• При одобрении тебя пригласят на обзвон.\n"
            "• Следи за личными сообщениями Discord.\n"
            "• Повторная подача после отказа — через 3 дня.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Нажми кнопку ниже, чтобы заполнить анкету."
        ),
        color=COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Holomatrix • Набор в семью")
    return embed


def portfolio_embed():
    embed = discord.Embed(
        title="Личное портфолио",
        description=(
            "Создай приватное пространство для своих игровых материалов.\n\n"
            "**Разделы портфеля:**\n"
            "📋・РП отчёты — отчёты и подтверждения\n"
            "⚔️・Арена — результаты и скриншоты\n"
            "🎥・Откаты с компетитив — видео и доказательства\n"
            "💬・Чат — обсуждение материалов\n\n"
            "Доступ будет у владельца портфеля и уполномоченного персонала."
        ),
        color=COLOR,
    )
    embed.set_footer(text="PORTLAND • Портфолио игроков")
    return embed


async def send_application_panel(channel):
    if APPLICATION_BANNER_URL:
        banner = discord.Embed(color=COLOR)
        banner.set_image(url=APPLICATION_BANNER_URL)
        await channel.send(embed=banner)
    await channel.send(embed=panel_embed(), view=ApplicationPanelView())


async def send_result_log(guild, title, applicant, moderator, reason=None, color=None):
    channel = get_channel(guild, RESULTS_CHANNEL_ID, discord.TextChannel)
    if not channel:
        return

    embed = discord.Embed(
        title=title,
        color=color or ACCENT,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="Заявитель",
        value=applicant.mention if applicant else "Пользователь покинул сервер",
        inline=False,
    )
    embed.add_field(name="Модератор", value=moderator.mention, inline=False)
    if reason:
        embed.add_field(name="Причина", value=reason[:1024], inline=False)
    embed.set_footer(text="Holomatrix • Система рассмотрения заявок")

    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        log.exception("Не удалось записать результат заявки")


class ApplicationModal(discord.ui.Modal, title="Анкета в семью"):
    nickname = discord.ui.TextInput(
        label="НИК | СТАТИК",
        placeholder="Игровой ник и статик",
        max_length=100,
    )
    families = discord.ui.TextInput(
        label="В каких семьях был",
        placeholder="Предыдущие семьи и причины ухода",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )
    characters = discord.ui.TextInput(
        label="Скриншоты персонажей (ссылка)",
        placeholder="Ссылка на скриншоты персонажей",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = get_channel(guild, APPLICATION_CATEGORY_ID, discord.CategoryChannel)
        if not guild or not category:
            await deny(interaction, "Категория заявок не найдена. Проверь ID категории.")
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
        }
        for role in guild.roles:
            if role.id in STAFF_ROLES:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True,
                )
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            )

        channel = None
        try:
            channel = await guild.create_text_channel(
                name=f"заявка-{safe_name(interaction.user.name)}",
                category=category,
                overwrites=overwrites,
                topic=f"APPLICATION_OWNER:{interaction.user.id}",
                reason=f"Заявка от {interaction.user}",
            )
            embed = discord.Embed(
                title="Новая заявка в семью",
                description="Заявка ожидает рассмотрения рекрута.",
                color=ACCENT,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Заявитель", value=interaction.user.mention, inline=False)
            embed.add_field(name="НИК | СТАТИК", value=self.nickname.value, inline=False)
            embed.add_field(name="В каких семьях был", value=self.families.value, inline=False)
            embed.add_field(
                name="Скриншоты персонажей",
                value=self.characters.value,
                inline=False,
            )
            embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

            await channel.send(
                content="<@&1388962793042214942>",
                embed=embed,
                view=ApplicationView(),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            await interaction.followup.send(
                f"✅ Заявка отправлена: {channel.mention}",
                ephemeral=True,
            )
        except discord.HTTPException:
            log.exception("Не удалось создать заявку")
            if channel:
                try:
                    await channel.delete(reason="Ошибка создания заявки")
                except discord.HTTPException:
                    log.warning("Не удалось удалить незавершённый канал заявки")
            await interaction.followup.send(
                "❌ Не удалось создать заявку. Проверь права бота и настройки категории.",
                ephemeral=True,
            )


class RejectModal(discord.ui.Modal, title="Причина отказа"):
    reason = discord.ui.TextInput(
        label="Причина отказа",
        placeholder="Укажи причину отказа",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, applicant_id: int):
        super().__init__()
        self.applicant_id = applicant_id

    async def on_submit(self, interaction: discord.Interaction):
        if not is_staff(interaction.user):
            await deny(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        applicant = guild.get_member(self.applicant_id) if guild else None

        if applicant:
            try:
                await applicant.send(
                    "❌ Твоя заявка в семью отклонена.\n"
                    f"**Причина:** {self.reason.value}\n"
                    "Повторная подача возможна через 3 дня."
                )
            except discord.HTTPException:
                pass

        await send_result_log(
            guild, "❌ Заявка отклонена", applicant, interaction.user,
            self.reason.value, discord.Color.red(),
        )
        await interaction.followup.send("Заявка отклонена.", ephemeral=True)

        if interaction.channel:
            try:
                await interaction.channel.delete(reason="Заявка отклонена")
            except discord.HTTPException:
                log.exception("Не удалось удалить канал отклонённой заявки")


class ApplicationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction):
        if not is_staff(interaction.user):
            await deny(interaction, "Только рекрут и выше может рассматривать заявки.")
            return False
        return True

    @discord.ui.button(
        label="Принять", emoji="✅", style=discord.ButtonStyle.success,
        custom_id="application:accept",
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        applicant_id = get_applicant_id(interaction.channel)
        if not applicant_id:
            await deny(interaction, "Не удалось определить автора заявки.")
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        applicant = guild.get_member(applicant_id) if guild else None

        if applicant:
            try:
                await applicant.send(
                    "✅ Твоя заявка в семью принята! Ожидай дальнейших инструкций от рекрута."
                )
            except discord.HTTPException:
                pass

        await send_result_log(
            guild, "✅ Заявка принята", applicant, interaction.user,
            color=discord.Color.green(),
        )
        await interaction.followup.send("Заявка принята.", ephemeral=True)

        if interaction.channel:
            try:
                await interaction.channel.delete(reason="Заявка принята")
            except discord.HTTPException:
                log.exception("Не удалось удалить канал принятой заявки")

    @discord.ui.button(
        label="Отклонить", emoji="❌", style=discord.ButtonStyle.danger,
        custom_id="application:reject",
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        applicant_id = get_applicant_id(interaction.channel)
        if not applicant_id:
            await deny(interaction, "Не удалось определить автора заявки.")
            return
        await interaction.response.send_modal(RejectModal(applicant_id))

    @discord.ui.button(
        label="Вызвать на обзвон", emoji="📞", style=discord.ButtonStyle.secondary,
        custom_id="application:call",
    )
    async def call(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        applicant_id = get_applicant_id(interaction.channel)
        if not guild or not applicant_id:
            await deny(interaction, "Не удалось определить заявку.")
            return

        channels = guild.voice_channels[:25]
        if not channels:
            await deny(interaction, "На сервере нет голосовых каналов.")
            return

        select = discord.ui.Select(
            placeholder="Выберите голосовой канал",
            options=[
                discord.SelectOption(label=channel.name[:100], value=str(channel.id))
                for channel in channels
            ],
        )
        view = discord.ui.View(timeout=120)
        view.add_item(select)

        async def select_callback(select_interaction: discord.Interaction):
            if not is_staff(select_interaction.user):
                await deny(select_interaction)
                return

            voice = guild.get_channel(int(select.values[0]))
            applicant = guild.get_member(applicant_id)
            if applicant and isinstance(voice, discord.VoiceChannel):
                try:
                    await applicant.send(
                        "📞 Тебя приглашают на обзвон.\n"
                        f"Голосовой канал: **{voice.name}**."
                    )
                except discord.HTTPException:
                    pass

            await select_interaction.response.send_message(
                "Уведомление отправлено, если у пользователя открыты личные сообщения.",
                ephemeral=True,
            )

        select.callback = select_callback
        await interaction.response.send_message(
            "Выбери голосовой канал для обзвона:",
            view=view,
            ephemeral=True,
        )


async def create_portfolio_for(
    guild: discord.Guild,
    user: discord.Member,
    nickname=None,
    static=None,
):
    if not guild:
        raise ValueError("Сервер не найден.")

    categories = get_portfolio_categories(guild)
    if not categories:
        raise ValueError("Исходная категория портфелей не найдена.")

    owner_marker = f"PORTFOLIO_OWNER:{user.id}"
    existing = next(
        (
            channel
            for category in categories
            for channel in category.text_channels
            if channel.topic and owner_marker in channel.topic
        ),
        None,
    )
    if existing:
        return existing, []

    category = await get_portfolio_category(guild)
    portfolio_name = (
        f"{nickname}-{static}" if nickname and static else user.display_name
    )

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            create_public_threads=True,
            send_messages_in_threads=True,
        ),
    }
    for role in guild.roles:
        if role.id in STAFF_ROLES:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
                manage_threads=True,
                send_messages_in_threads=True,
            )
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_threads=True,
            create_public_threads=True,
            send_messages_in_threads=True,
        )

    channel = await guild.create_text_channel(
        name=f"📁-портфель-{safe_name(portfolio_name)}",
        category=category,
        overwrites=overwrites,
        topic=(
            f"PORTFOLIO_OWNER:{user.id} | "
            f"НИК: {nickname or user.display_name} | "
            f"СТАТИК: {static or 'не указан'}"
        ),
        reason=f"Портфель для {user}",
    )

    threads = []
    try:
        for name in PORTFOLIO_THREADS:
            message = await channel.send(
                f"**{name}**\nИспользуйте эту ветку для материалов по теме."
            )
            thread = await message.create_thread(
                name=name,
                auto_archive_duration=1440,
            )
            threads.append(thread)
    except discord.HTTPException:
        try:
            await channel.delete(reason="Ошибка создания портфеля")
        except discord.HTTPException:
            log.exception("Не удалось удалить незавершённый портфель")
        raise

    return channel, threads


class PortfolioModal(discord.ui.Modal, title="Создание портфеля"):
    nickname = discord.ui.TextInput(
        label="Игровой ник", placeholder="Введите игровой ник", max_length=32
    )
    static = discord.ui.TextInput(
        label="Статик", placeholder="Введите статик", max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await deny(interaction, "Форма доступна только участникам сервера.")
            return

        nickname = self.nickname.value.strip()
        static = self.static.value.strip()
        if not nickname or not static:
            await deny(interaction, "Заполни ник и статик.")
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            channel, threads = await create_portfolio_for(
                interaction.guild, interaction.user, nickname, static
            )
            if not threads:
                await interaction.followup.send(
                    f"У тебя уже есть портфель: {channel.mention}",
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                f"✅ Портфель создан: {channel.mention}\n"
                + "\n".join(thread.mention for thread in threads),
                ephemeral=True,
            )
        except (discord.HTTPException, ValueError):
            log.exception("Не удалось создать портфель")
            await interaction.followup.send(
                "❌ Не удалось создать портфель. Проверь права бота и категорию.",
                ephemeral=True,
            )


class ApplicationPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Подать заявку",
        style=discord.ButtonStyle.secondary,
        custom_id="application:open",
    )
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(ApplicationModal())
        except discord.HTTPException:
            log.exception("Не удалось открыть анкету для %s", interaction.user.id)


class PortfolioPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Создать портфель",
        emoji="📁",
        style=discord.ButtonStyle.secondary,
        custom_id="portfolio:create",
    )
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(PortfolioModal())
        except discord.HTTPException:
            log.exception("Не удалось открыть форму портфеля для %s", interaction.user.id)


@bot.tree.command(name="zayavka", description="Создать панель подачи заявок в семью")
async def zayavka(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        await deny(interaction)
        return
    if not interaction.channel:
        await deny(interaction, "Канал не найден.")
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await send_application_panel(interaction.channel)
        await interaction.followup.send("✅ Панель заявок опубликована.", ephemeral=True)
    except discord.HTTPException:
        log.exception("Не удалось опубликовать панель заявок")
        await interaction.followup.send(
            "❌ Не удалось опубликовать панель. Проверь права бота.",
            ephemeral=True,
        )


@bot.tree.command(name="setup", description="Создать панель портфелей")
async def setup_portfolio(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        await deny(interaction)
        return
    if not interaction.channel:
        await deny(interaction, "Канал не найден.")
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await interaction.channel.send(
            embed=portfolio_embed(),
            view=PortfolioPanelView(),
        )
        await interaction.followup.send(
            "✅ Панель портфелей опубликована.",
            ephemeral=True,
        )
    except discord.HTTPException:
        log.exception("Не удалось опубликовать панель портфелей")
        await interaction.followup.send(
            "❌ Не удалось опубликовать панель. Проверь права бота.",
            ephemeral=True,
        )


@bot.tree.command(name="create_portfolio", description="Создать портфель пользователю")
@app_commands.describe(user="Пользователь, которому создаётся портфель")
async def create_portfolio_command(
    interaction: discord.Interaction,
    user: discord.Member,
):
    if not is_staff(interaction.user):
        await deny(interaction)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        channel, threads = await create_portfolio_for(interaction.guild, user)
        if not threads:
            await interaction.followup.send(
                f"У {user.mention} уже есть портфель: {channel.mention}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Портфель для {user.mention}: {channel.mention}\n"
            + "\n".join(thread.mention for thread in threads),
            ephemeral=True,
        )
    except (discord.HTTPException, ValueError):
        log.exception("Не удалось создать портфель командой")
        await interaction.followup.send(
            "❌ Не удалось создать портфель. Проверь права бота и категорию.",
            ephemeral=True,
        )


@bot.event
async def on_ready():
    if getattr(bot, "_synced_once", False):
        return
    try:
        synced = await bot.tree.sync()
        bot._synced_once = True
        log.info("Вход выполнен: %s | команд: %s", bot.user, len(synced))
    except discord.HTTPException:
        log.exception("Не удалось синхронизировать команды")


async def main():
    if not TOKEN:
        raise RuntimeError("Добавь токен бота в переменную окружения DISCORD_TOKEN.")

    async with bot:
        bot.add_view(ApplicationPanelView())
        bot.add_view(PortfolioPanelView())
        bot.add_view(ApplicationView())
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
