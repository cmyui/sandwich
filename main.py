#!/usr/bin/env python3.10
"""sandwich - a discord bot i've built for my personal needs; mostly python.

repo: https://github.com/cmyui/sandwich
"""

__author__ = "Joshua Smith (cmyui)"
__email__ = "cmyuiosu@gmail.com"

import asyncio
import contextlib
import datetime
import dis
import io
import os
import platform
import pprint
import random
import shlex
import subprocess
import sys
import traceback
import urllib.parse
import zipfile
from collections import namedtuple
from types import FunctionType
from typing import Optional

import aiohttp
import cpuinfo
import discord
import openai
import index_analysis
import orjson
import timeago
from discord.ext import commands

import config


openai.api_key = os.getenv("OPENAI_API_KEY")

SANDWICH_TOPPINGS = [
    "tomatoes",
    "lettuce",
    "ham",
    "chicken",
    "cheese",
    "mayonaise",
    "pickles",
    "pumpernickel",
    "tomaten chutney",
    "hot italian giardiniera",
    "egg escabeche",
    "goat cheese",
    "philly cheese steak",
    "corned beef",
    "tarragon yoghurt dressing",
    "turkey argula",
]

# what is this lol
NO = (
    "thou may not take thy toothpick",
    "no",
    "yo m",
    "mask off",
    *[f"u may not taste my delicious {t}" for t in SANDWICH_TOPPINGS],
)

ORDER_SUFFIXES = ["K", "M", "B", "T", "Q"]


def magnitude_fmt(n: float) -> str:
    for suffix in ORDER_SUFFIXES:
        n /= 1000
        if n < 1000:
            return f"{n:,.3f}{suffix}"
    else:
        # what? we need quintillions? lol
        raise NotImplementedError(f"{n} too big.")


# finance stuff


def sp500_analysis(
    start_date: datetime.date,
    end_date: datetime.date,
    starting_balance: float,
    monthly_contributions: float,
) -> str:
    results = index_analysis.analysis.do_analysis(
        start_date=start_date,
        end_date=end_date,
        starting_balance=starting_balance,
        monthly_contributions=monthly_contributions,
    )

    new_balance = results["ending_balance"] / results["ending_inflation"]

    return (
        f"Estimated value after {timeago.format(end_date, start_date)} "
        f"(adjusted for inflation): ${new_balance:,.2f}\n"
        "⛹️‍♂️ https://investor.vanguard.com/etf/profile/VOO"
    )


class Context(commands.Context):
    async def send(
        self, content=None, force_new=False, **kwargs
    ) -> Optional[discord.Message]:
        assert self.message is not None
        assert self.bot is not None

        bot_msg: discord.Message

        if force_new or self.message.id not in self.bot.cache["resp"]:
            bot_msg = await super().send(content, **kwargs)

            if not force_new:  # don't save forced msgs
                self.bot.cache["resp"][self.message.id] = bot_msg
        else:
            bot_msg = self.bot.cache["resp"][self.message.id]
            embed = kwargs.get("embed", None)

            # if no new content or embed provided, delete
            # the cached bot message from chat & cache.
            if not (embed or content):
                await bot_msg.delete()
                del self.bot.cache["resp"][self.message.id]
                return

            content = content or bot_msg.content
            await bot_msg.edit(content=content, embed=embed)

        return bot_msg


def get_code_from_message_content(
    content: str,
    prefix: str,
    invoked_with: str,
) -> str:
    """Extract the code text from a discord message's content."""
    cmd_text = content.removeprefix(f"{prefix}{invoked_with} ").strip()

    if cmd_text.startswith("```"):
        # multi-line code block
        assert cmd_text.endswith("```"), "Invalid rich code block"

        cmd_text = cmd_text.removeprefix("```")
        cmd_text = cmd_text.removesuffix("```")

        # rich syntax
        for lang_id in ("py", "python"):
            if cmd_text.startswith(f"{lang_id}\n"):
                cmd_text = cmd_text.removeprefix(f"{lang_id}\n")
    elif cmd_text.startswith("`"):
        # code block
        assert cmd_text.endswith("`"), "Invalid code block"

        cmd_text = cmd_text.removeprefix("`")
        cmd_text = cmd_text.removesuffix("`")
    else:
        # plaintext
        pass

    # replace sequences of newlines with a single newline
    cmd_text = "\n".join(l for l in cmd_text.split("\n") if l)

    # strip any whitespace & newlines from the text
    cmd_text = cmd_text.strip("`\n\t ")

    return cmd_text


@contextlib.contextmanager
def capture_stdout(buffer: io.StringIO):
    # write to buffer rather than real
    # stdout while we're in this block
    real_stdout = sys.stdout
    sys.stdout = buffer

    try:
        yield
    finally:
        # return to real stdout
        sys.stdout = real_stdout
        buffer.seek(0)


# used for saving values in `Commands().namespace` from !py land
SavedValue = namedtuple("SavedValue", ["name", "value"])


def _save(k: str, v: object) -> SavedValue:
    return SavedValue(k, v)


def _saved(g: dict[str, object]) -> dict[str, object]:
    return {k: g[k] for k in set(g) - {"__builtins__", "__py"}}


class Commands(commands.Cog):
    def __init__(self, bot: "Sandwich") -> None:
        self.bot = bot

        # some people allowed to use dangerous
        # commands by default, this would be a
        # security risk on a 'real' bot.
        uname = os.uname()

        self.whitelist = {
            285190493703503872,  # cmyui
        }

        if not (uname.nodename == "cmyui" or "microsoft-standard-WSL" in uname.release):
            self.whitelist |= {
                828821094559514600,  # cover
                347459855449325570,  # flame
                455300278120480800,  # cherry
                263413454709194753,  # realistik
                272111921610752003,  # james
                291927822635761665,  # lenforiee
                153954447247147018,  # rapha
            }
            self.whitelist_ai = {
                109573180867252224,
                597404438721986560,
                1011439359083413564,
            }
        # a dict for our global variables within the !py command.
        # by default, this has functions to save vars, retrieve saved ones,
        self.namespace = {
            "save": _save,
            "saved": _saved,
            "sp500_analysis": sp500_analysis,
        }
        # and also contains frequently used modules for ease of access.
        # TODO: some better way to do this
        for mod_name in (
            "aiohttp",
            "ast",
            "astpretty",
            "asyncio",
            "os",
            "sys",
            "struct",
            "discord",
            "cmyui",
            "datetime",
            "collections",
            "time",
            "inspect",
            "math",
            "psutil",
            "re",
            "pickle",
            "dill",
            "signal",
            "numpy",
            "socket",
            "random",
            "pprint",
            "pathlib",
            "hashlib",
            "platform",
            "cpuinfo",
            "bcrypt",
            "orjson",
        ):
            try:  # only use ones that're already installed
                self.namespace[mod_name] = __import__(mod_name)
            except ModuleNotFoundError:
                pass

    @commands.command(name="g")
    async def google(self, ctx: Context) -> None:
        assert ctx.message is not None

        invoked_with = "{prefix}{invoked_with} ".format(**ctx.__dict__)
        content = urllib.parse.quote_plus(
            ctx.message.content.removeprefix(invoked_with),
        ).strip()

        await ctx.send(f"https://google.com/search?q={content}")

    @commands.is_owner()
    @commands.command()
    async def restart(self, ctx: Context) -> None:
        assert ctx.message is not None

        await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.is_owner()
    @commands.command()
    async def addwl(self, ctx: Context) -> None:
        assert ctx.message is not None

        self.whitelist |= set([m.id for m in ctx.message.mentions])
        await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

    @commands.is_owner()
    @commands.command()
    async def rmwl(self, ctx: Context) -> None:
        assert ctx.message is not None

        self.whitelist -= set([m.id for m in ctx.message.mentions])
        await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

    @commands.command()
    async def genimage(self, ctx: Context) -> None:
        whitelist = self.whitelist | self.whitelist_ai

        if ctx.author.id not in whitelist:
            await ctx.send(random.choice(NO))
            return

        assert ctx.message is not None
        assert ctx.invoked_with is not None

        prompt = ctx.message.content.removeprefix(
            f"{ctx.prefix}{ctx.invoked_with} "
        ).strip()

        openai.api_key = os.getenv("OPENAI_API_KEY")
        response = openai.Image.create(prompt=prompt, n=1, size="1024x1024")

        # TODO: price?

        await ctx.send(response.data[0].url)

    @commands.command()
    async def askai(self, ctx: Context) -> None:
        whitelist = self.whitelist | self.whitelist_ai

        if ctx.author.id not in whitelist:
            await ctx.send(random.choice(NO))
            return

        assert ctx.message is not None
        assert ctx.invoked_with is not None

        prompt = ctx.message.content.removeprefix(
            f"{ctx.prefix}{ctx.invoked_with} "
        ).strip()

        for attachment in ctx.message.attachments:
            # only accept text
            if attachment.content_type in (
                "text/plain",
                "text/markdown",
                "text/x-python",
            ):
                prompt += "\n\n" + (await attachment.read()).decode()

        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=prompt,
            temperature=0.9,  # TODO: configurable
            max_tokens=2048,  # TODO: configurable?
        )
        if len(response.choices) != 1:
            print("More than 1 choice!")
            print("\n\n", response.choices, "\n\n")

        response_text = response.choices[0].text.lstrip("\n")
        cents_spent = (response.usage.total_tokens * (0.02 / 1000)) * 100

        if len(response_text) > 2000:
            with io.StringIO(response_text) as f:
                response_file = discord.File(f, "response.txt")
                await ctx.send(
                    f"Spent {cents_spent:.5f}¢ ({response.usage.total_tokens} tokens) to produce result:",
                    file=response_file,
                )

            return

        await ctx.send(
            f"Spent {cents_spent:.5f}¢ ({response.usage.total_tokens} tokens) to produce result:\n\n{response_text}"
        )

    @commands.command()
    async def dis(self, ctx: Context) -> None:
        if ctx.author.id not in self.whitelist:
            await ctx.send(random.choice(NO))
            return

        assert ctx.message is not None
        assert ctx.invoked_with is not None

        try:
            code_text = get_code_from_message_content(
                ctx.message.content,
                ctx.prefix,
                ctx.invoked_with,
            )
        except AssertionError as exc:
            await ctx.send(exc.args[0])
            return

        namespace = {}

        try:
            exec(code_text, namespace)
        except:
            await ctx.send(f"```\n{traceback.format_exc()}```")
            await ctx.message.add_reaction("\N{CROSS MARK}")
            return

        # ran successfully.
        await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

        if "func" not in namespace:
            await ctx.send("No variable named `func` in namespace.")
            return

        func = namespace["func"]

        if not isinstance(func, FunctionType):
            await ctx.send("Variable in namespace must be a function.")
            return

        # capture stdout
        with io.StringIO() as buffer:
            with capture_stdout(buffer):
                dis.dis(func)

            disassembly = buffer.read(-1)

        if disassembly is None:
            # clear any previous responses
            await ctx.send(None)
            return

        await ctx.send(f"```py\n{disassembly}```")

    @commands.command()
    async def timeit(self, ctx: Context) -> None:
        """Parse & execute python timeit module via bash."""
        if ctx.author.id not in self.whitelist:
            await ctx.send(random.choice(NO))
            return

        assert ctx.message is not None
        assert ctx.invoked_with is not None

        invoked_with = "{prefix}{invoked_with} ".format(**ctx.__dict__)
        cmd_txt = ctx.message.content.removeprefix(invoked_with)

        try:
            bash_args = shlex.split(f"{sys.executable} -m timeit {cmd_txt}")
        except ValueError as exc:
            await ctx.send(f"{exc.args[0]}.")
            return

        # NOTE: to get accurate results here we have to block
        p = subprocess.Popen(
            args=bash_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate()

        if stderr:
            await ctx.send(f"```py\n{stderr.decode()}```")
        elif stdout:
            cpu_info = cpuinfo.get_cpu_info()

            cpu_name = cpu_info["brand_raw"]
            if not cpu_name.endswith("GHz"):
                cpu_ghz = cpu_info["hz_advertised"][0] / (1000**3)
                cpu_name += f" @ {cpu_ghz:.2f} GHz"

            await ctx.send(
                "{cpu_name} | {python_impl} v{python_version}\n{output}".format(
                    **cpu_info,
                    cpu_name=cpu_name,
                    output=stdout.decode(),
                    python_impl=platform.python_implementation(),
                ),
            )

    @commands.command()
    async def py(self, ctx: Context) -> None:
        """Parse & execute message via python interpreter."""
        if ctx.author.id not in self.whitelist:
            await ctx.send(random.choice(NO))
            return

        assert ctx.message is not None
        assert ctx.invoked_with is not None

        try:
            code_text = get_code_from_message_content(
                ctx.message.content,
                ctx.prefix,
                ctx.invoked_with,
            )
        except AssertionError as exc:
            await ctx.send(exc.args[0])
            return

        code_text = f" {code_text}".replace("\n", "\n ")  # indent func code
        func_def = f"async def __py(ctx):\n{code_text}"

        try:
            exec(func_def, self.namespace)  # compile function
            ret = await self.namespace["__py"](ctx)  # await it's return
        except:
            await ctx.send(f"```{traceback.format_exc()}```")
            await ctx.message.add_reaction("\N{CROSS MARK}")
            return
        else:
            # !py ran successfully.
            await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        finally:
            if "__py" in self.namespace:
                del self.namespace["__py"]

        if ret is None:
            # clear any previous responses
            await ctx.send(None)
            return

        # the return value may be from the !save command.
        if isinstance(ret, SavedValue):
            # NOTE: this will overwrite preexisting vars.
            self.namespace[ret.name] = ret.value
            await ctx.send(f"Added `{ret.name}` to namespace.")
        else:
            truncated = False

            if not isinstance(ret, str):
                # XXX: perhaps i could truncate here as well?
                # i'll see how it's use goes in practice
                oversize = sys.getsizeof(ret) - (3 * 1024)  # 3KB
                if oversize > 0:
                    await ctx.send(f"Response {oversize}B too large (max 3KB).")
                    return

                ret = pprint.pformat(ret, compact=True)
            else:
                if len(ret) > 10000:
                    await ctx.send("Response way too long.")
                    return

            # discord content len limited to 2k chars.
            if len(ret) > 2000:
                ret = ret[:2000]
                truncated = True

            await ctx.send(ret)

            if truncated:
                await ctx.send(
                    "(Message truncated to 2k characters)",
                    force_new=True,
                    delete_after=3.5,
                )

    @commands.command()
    async def gitlines(self, ctx: Context) -> None:
        """Retrieve the linecounts (code, comments) for a given repo & lang."""
        # NOTE: this is quite inaccurate, as doing this correctly
        # would basically require parsing the code for each lang lol.
        # it's just made to get the general idea of the size/ratio.
        assert ctx.message is not None

        if len(msg := ctx.message.content.split(" ")[1:]) < 2:
            await ctx.send("Invalid syntax: !gitlines <repo> <file extensions ...>")
            return

        # TODO: better multi-line support
        lang_comments = {
            "py": {"single": "#", "multi": ('"""', "'''")},  # wrong but okay for now
            "pyx": {"single": "#", "multi": ('"""', "'''")},
            #'go': {'single': '//', 'multi': ()},
            #'js': {'single': '//', 'multi': ()},
            #'ts': {'single': '//', 'multi': ()},
        }

        repo, *exts = msg

        if not all([ext in lang_comments for ext in exts]):
            await ctx.send(f"supported exts: {set(lang_comments)}.")
            return

        # repo may contain branch
        if repo.count("/") == 2:
            repo, branch = repo.rsplit("/", maxsplit=1)
        else:
            branch = "master"

        repo_url = f"https://github.com/{repo}/archive/{branch}.zip"

        async with self.bot.http_sess.get(repo_url) as resp:
            if resp.status != 200:
                await ctx.send(
                    f'Failed to find repo "{repo}/{branch}" ({resp.status}).',
                )
                return

            if resp.content_type != "application/zip":
                await ctx.send(f"Invalid response (CT: {resp.content_type}).")
                return

            size_MB = resp.content.total_bytes // (1024**3)

            if size_MB >= 2:
                await ctx.send(f"Repo too big ({size_MB:,.2f}MB).")
                return

            resp_content = await resp.read()

        with io.BytesIO(resp_content) as data:
            try:
                repo_zip = zipfile.ZipFile(data)
            except Exception as e:
                print(e)
                return

            line_counts = {ext: {"code": 0, "comments": 0} for ext in exts}

            for file in repo_zip.filelist:
                for ext in exts:
                    if (fname := file.filename).endswith(ext):
                        break
                else:  # not an ext we care abt
                    continue

                if ext not in lang_comments:
                    await ctx.send(f"*.{ext} not yet supported.")
                    return

                if not (f_content := repo_zip.read(file)):
                    continue

                comments = lang_comments[ext]
                single_line_comment = comments["single"]
                multi_line_comment = comments["multi"]

                code_lines = comment_lines = 0
                in_multi_line_comment = False

                lines = f_content.decode().splitlines()

                # TODO: more languages supported & multi-line comments
                for line in [l.strip() for l in lines if l]:
                    if line.startswith(multi_line_comment):
                        in_multi_line_comment = not in_multi_line_comment

                    if in_multi_line_comment:
                        comment_lines += 1
                        # end of multi line comment
                        if len(line) != 3 and line.endswith(multi_line_comment):
                            in_multi_line_comment = False
                        continue

                    if line.startswith(single_line_comment):
                        comment_lines += 1
                    else:
                        code_lines += 1

                line_counts[ext]["code"] += code_lines
                line_counts[ext]["comments"] += comment_lines

        await ctx.send(
            "Total linecounts (inaccurate):\n"
            + "\n".join(f"{k} | {v}" for k, v in line_counts.items()),
        )

    @commands.command()
    async def ns(self, ctx: Context) -> None:  # nuke self's messages
        assert ctx.message is not None

        is_bot = lambda m: m.author == self.bot.user
        await ctx.channel.purge(check=is_bot, limit=1000)
        await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

    @commands.command()
    async def nr(self, ctx: Context) -> None:  # nuke reactions
        async for msg in ctx.history():
            await msg.clear_reactions()

    @commands.command()
    async def how(self, ctx: Context) -> None:
        await ctx.send("magic")


class Sandwich(commands.Bot):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.http_sess: aiohttp.ClientSession

        self.cache = {"resp": {}}  # many kinds

        self.add_cog(Commands(self))

    async def run(self, token: str, *args, **kwargs) -> None:
        self.http_sess = aiohttp.ClientSession(
            json_serialize=lambda x: orjson.dumps(x).decode(),
        )

        try:
            await self.start(token, *args, **kwargs)
        except:
            await self.http_sess.close()
            await self.close()

    async def process_commands(self, msg: discord.Message) -> None:
        if msg.author.bot:
            # don't process messages for bots
            return

        ctx = await self.get_context(msg, cls=Context)
        await self.invoke(ctx)

    async def on_ready(self):
        print(f"\x1b[0;92m{self.user} up\x1b[0m")

    async def on_message(self, msg: discord.Message) -> None:
        await self.process_commands(msg)

    async def on_message_edit(
        self,
        before: discord.Message,
        after: discord.Message,
    ) -> None:
        await self.process_commands(after)

    async def on_message_delete(self, msg: discord.Message) -> None:
        if previous_resp := self.cache["resp"].pop(msg.id, None):
            await previous_resp.delete()

    async def on_command_error(
        self,
        ctx: Context,
        error: commands.CommandError,
    ) -> None:
        if not isinstance(
            error,
            commands.errors.CommandNotFound,
        ):  # ignore unknown cmds
            return await super().on_command_error(ctx, error)


async def main() -> int:
    # set cwd to main directory
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    bot = Sandwich(command_prefix="!", help_command=None)
    await bot.run(config.discord_token)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
