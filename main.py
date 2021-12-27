#!/usr/bin/python3.10
# -*- coding: utf-8 -*-

"""my personal (messy) discord bot. made (and great) for functionality."""

import asyncio
import contextlib
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
import zipfile
from collections import namedtuple
from types import FunctionType
from typing import Optional, Union

import aiohttp
import cmyui
import cpuinfo
import discord
import orjson
from cmyui import Ansi, log
from discord.ext import commands

import config

CMYUI_ID = 285190493703503872
COVER_ID = 828821094559514684
FLAME_ID = 347459855449325570
CHERRY_ID = 455300278120480770
REALISTIK_ID = 263413454709194753

SANDWICH_TOPPINGS = [
    'tomatoes', 'lettuce', 'ham', 'chicken', 'cheese',
    'mayonaise', 'pickles', 'pumpernickel', 'tomaten chutney',
    'hot italian giardiniera', 'egg escabeche', 'goat cheese',
    'philly cheese steak', 'corned beef', 'tarragon yoghurt dressing',
    'turkey argula'
]

# what is this lol
NO = (
    'thou may not take thy toothpick',
    'no',
    'yo m',
    'mask off',
    *[f'u may not taste my delicious {t}' for t in SANDWICH_TOPPINGS]
)

ORDER_SUFFIXES = ['K', 'M', 'B', 'T', 'Q']
def magnitude_fmt(n: float) -> str:
    for suffix in ORDER_SUFFIXES:
        n /= 1000
        if n < 1000:
            return f'{n:,.3f}{suffix}'
    else:
        # what? we need quintillions? lol
        raise NotImplementedError(f"{n} too big.")

# finance stuff

# TODO: let user pass in how many years to calc avg from?
AVG_SP500_50Y_RETURN = 10.9 / 100
def sp500_returns(principal: Union[int, float], years: int) -> str:
    A = principal * (1 + (AVG_SP500_50Y_RETURN / 1)) ** (1 * years)

    if A > 1_000_000_000_000_000:
        return 'Too lazy to support >= 1 quadrillion.'

    return (f'Estimated value after {years}yrs: ${A:,.2f} ({magnitude_fmt(A)}) ⛹️‍♂️\n'
            'https://investor.vanguard.com/etf/profile/VOO')

class Context(commands.Context):
    async def send(self, content = None, force_new = False,
                   **kwargs) -> Optional[discord.Message]:
        bot_msg: discord.Message

        if force_new or self.message.id not in self.bot.cache['resp']:
            bot_msg = await super().send(content, **kwargs)

            if not force_new: # don't save forced msgs
                self.bot.cache['resp'][self.message.id] = bot_msg
        else:
            bot_msg = self.bot.cache['resp'][self.message.id]
            embed = kwargs.get('embed', None)

            # if no new content or embed provided, delete
            # the cached bot message from chat & cache.
            if not (embed or content):
                await bot_msg.delete()
                del self.bot.cache['resp'][self.message.id]
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
    cmd_text = content.removeprefix(f'{prefix}{invoked_with} ').strip()

    if cmd_text.startswith('```'):
        # multi-line code block
        assert cmd_text.endswith('```'), 'Invalid rich code block'

        cmd_text = cmd_text.removeprefix('```')
        cmd_text = cmd_text.removesuffix('```')

        # rich syntax
        for lang_id in ('py', 'python'):
            if cmd_text.startswith(f'{lang_id}\n'):
                cmd_text = cmd_text.removeprefix(f'{lang_id}\n')
    elif cmd_text.startswith('`'):
        # code block
        assert cmd_text.endswith('`'), 'Invalid code block'

        cmd_text = cmd_text.removeprefix('`')
        cmd_text = cmd_text.removesuffix('`')
    else:
        # plaintext
        pass

    # replace sequences of newlines with a single newline
    cmd_text = '\n'.join(l for l in cmd_text.split('\n') if l)

    # strip any whitespace & newlines from the text
    cmd_text = cmd_text.strip('`\n\t ')

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
SavedValue = namedtuple('SavedValue', ['name', 'value'])

def _save(k: str, v: object) -> SavedValue:
    return SavedValue(k, v)

def _saved(g: dict[str, object]) -> dict[str, object]:
    return {k: g[k] for k in set(g) - {'__builtins__', '__py'}}

class Commands(commands.Cog):
    def __init__(self, bot: 'Sandwich') -> None:
        self.bot = bot

        # some people allowed to use dangerous
        # commands by default, this would be a
        # security risk on a 'real' bot.
        uname = os.uname()

        self.whitelist = {CMYUI_ID}

        if not (
            uname.nodename == 'cmyui' or
            'microsoft-standard-WSL' in uname.release
        ):
            self.whitelist |= {
                COVER_ID, FLAME_ID,
                CHERRY_ID, REALISTIK_ID
            }

        # a dict for our global variables within the !py command.
        # by default, this has functions to save vars, retrieve saved ones,
        self.namespace = {'save': _save, 'saved': _saved,
                          'sp500_returns': sp500_returns}
        # and also contains frequently used modules for ease of access.
        for mod_name in (
            'aiohttp', 'ast', 'astpretty', 'asyncio', 'os',
            'sys', 'struct', 'discord', 'cmyui', 'datetime',
            'collections', 'time', 'inspect', 'math', 'psutil',
            're', 'pickle', 'dill', 'signal', 'numpy', 'socket',
            'random', 'pprint', 'pathlib', 'hashlib', 'platform',
            'cpuinfo', 'bcrypt', 'orjson'
        ):
            try: # only use ones that're already installed
                self.namespace[mod_name] = __import__(mod_name)
            except ModuleNotFoundError:
                pass

    @commands.is_owner()
    @commands.command()
    async def restart(self, ctx: Context):
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.is_owner()
    @commands.command()
    async def addwl(self, ctx: Context):
        self.whitelist |= set([m.id for m in ctx.message.mentions])
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    @commands.is_owner()
    @commands.command()
    async def rmwl(self, ctx: Context):
        self.whitelist -= set([m.id for m in ctx.message.mentions])
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

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
            await ctx.send(f'```\n{traceback.format_exc()}```')
            await ctx.message.add_reaction('\N{CROSS MARK}')
            return

        # ran successfully.
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

        del namespace['__builtins__']

        if len(namespace) != 1:
            await ctx.send('Only a single function may be defined in namespace.')
            return

        func = list(namespace.values())[0]

        if not isinstance(func, FunctionType):
            await ctx.send('Variable in namespace must be a function.')
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

        await ctx.send(f'```py\n{disassembly}```')


    @commands.command()
    async def timeit(self, ctx: Context) -> None:
        """Parse & execute python timeit module via bash."""
        if ctx.author.id not in self.whitelist:
            await ctx.send(random.choice(NO))
            return

        assert ctx.message is not None
        assert ctx.invoked_with is not None

        invoked_with = '{prefix}{invoked_with} '.format(**ctx.__dict__)
        cmd_txt = ctx.message.content.removeprefix(invoked_with)

        try:
            bash_args = shlex.split(f'{sys.executable} -m timeit {cmd_txt}')
        except ValueError as exc:
            await ctx.send(f'{exc.args[0]}.')
            return

        # NOTE: to get accurate results here we have to block
        p = subprocess.Popen(
            args=bash_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        stdout, stderr = p.communicate()

        if stderr:
            await ctx.send(f'```py\n{stderr.decode()}```')
        elif stdout:
            cpu_info = cpuinfo.get_cpu_info()

            cpu_name = cpu_info['brand_raw']
            if not cpu_name.endswith('GHz'):
                cpu_ghz = cpu_info['hz_advertised'][0] / (1000 ** 3)
                cpu_name += f' @ {cpu_ghz:.2f} GHz'

            await ctx.send('{cpu_name} | {python_impl} v{python_version}\n{output}'.format(
                **cpu_info,
                cpu_name=cpu_name,
                output=stdout.decode(),
                python_impl=platform.python_implementation()
            ))

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

        code_text = f' {code_text}'.replace('\n', '\n ') # indent func code
        func_def = f'async def __py(ctx):\n{code_text}'

        try:
            exec(func_def, self.namespace)             # compile function
            ret = await self.namespace['__py'](ctx) # await it's return
        except:
            await ctx.send(f'```{traceback.format_exc()}```')
            await ctx.message.add_reaction('\N{CROSS MARK}')
            return
        else:
            # !py ran successfully.
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
        finally:
            if '__py' in self.namespace:
                del self.namespace['__py']

        if ret is None:
            # clear any previous responses
            await ctx.send(None)
            return

        # the return value may be from the !save command.
        if isinstance(ret, SavedValue):
            # NOTE: this will overwrite preexisting vars.
            self.namespace[ret.name] = ret.value
            await ctx.send(f'Added `{ret.name}` to namespace.')
        else:
            truncated = False

            if not isinstance(ret, str):
                # XXX: perhaps i could truncate here as well?
                # i'll see how it's use goes in practice
                oversize = sys.getsizeof(ret) - (3 * 1024) # 3KB
                if oversize > 0:
                    await ctx.send(f'Response {oversize}B too large (max 3KB).')
                    return

                ret = pprint.pformat(ret,compact=True)
            else:
                if len(ret) > 10000:
                    await ctx.send('Response way too long.')
                    return

            # discord content len limited to 2k chars.
            if len(ret) > 2000:
                ret = ret[:2000]
                truncated = True

            await ctx.send(ret)

            if truncated:
                await ctx.send(
                    '(Message truncated to 2k characters)',
                    force_new=True, delete_after=3.5
                )

    @commands.command()
    async def gitlines(self, ctx: Context):
        """Retrieve the linecounts (code, comments) for a given repo & lang."""
        # NOTE: this is quite inaccurate, as doing this correctly
        # would basically require parsing the code for each lang lol.
        # it's just made to get the general idea of the size/ratio.
        if len(msg := ctx.message.content.split(' ')[1:]) < 2:
            await ctx.send('Invalid syntax: !gitlines <repo> <file extensions ...>')
            return

        # TODO: better multi-line support
        lang_comments = {
            'py': {'single': '#', 'multi': ('"""', "'''")}, # wrong but okay for now
            #'go': {'single': '//', 'multi': ()},
            #'js': {'single': '//', 'multi': ()},
            #'ts': {'single': '//', 'multi': ()},
        }

        repo, *exts = msg

        if not all([ext in lang_comments for ext in exts]):
            await ctx.send(f'supported exts: {set(lang_comments)}.')
            return

        # repo may contain branch
        if repo.count('/') == 2:
            repo, branch = repo.rsplit('/', maxsplit=1)
        else:
            branch = 'master'

        repo_url = f'https://github.com/{repo}/archive/{branch}.zip'

        async with self.bot.http_sess.get(repo_url) as resp:
            if resp.status != 200:
                await ctx.send(f'Failed to find repo "{repo}/{branch}" ({resp.status}).')
                return

            if resp.content_type != 'application/zip':
                await ctx.send(f'Invalid response (CT: {resp.content_type}).')
                return

            size_MB = resp.content.total_bytes // (1024 ** 3)

            if size_MB >= 2:
                await ctx.send(f'Repo too big ({size_MB:,.2f}MB).')
                return

            resp_content = await resp.read()

        with io.BytesIO(resp_content) as data:
            try:
                repo_zip = zipfile.ZipFile(data)
            except Exception as e:
                print(e)
                return

            line_counts = {ext: {'code': 0, 'comments': 0} for ext in exts}

            for file in repo_zip.filelist:
                for ext in exts:
                    if (fname := file.filename).endswith(ext):
                        break
                else: # not an ext we care abt
                    continue

                if ext not in lang_comments:
                    await ctx.send(f'*.{ext} not yet supported.')
                    return

                if not (f_content := repo_zip.read(file)):
                    continue

                comments = lang_comments[ext]
                single_line_comment = comments['single']
                multi_line_comment = comments['multi']

                code_lines = comment_lines = 0
                in_multi_line_comment = False

                lines = f_content.decode().splitlines()

                # TODO: more languages supported & multi-line comments
                for line in [l.strip() for l in lines if l]:
                    if line.startswith(multi_line_comment):
                        in_multi_line_comment = not in_multi_line_comment

                    if in_multi_line_comment:
                        comment_lines += 1
                        if ( # end of multi line comment
                            len(line) != 3 and
                            line.endswith(multi_line_comment)
                        ):
                            in_multi_line_comment = False
                        continue

                    if line.startswith(single_line_comment):
                        comment_lines += 1
                    else:
                        code_lines += 1

                line_counts[ext]['code'] += code_lines
                line_counts[ext]['comments'] += comment_lines

        await ctx.send('Total linecounts (inaccurate):\n' + '\n'.join(
            f'{k} | {v}' for k, v in line_counts.items()
        ))

    @commands.command()
    async def ns(self, ctx: Context): # nuke self's messages
        is_bot = lambda m: m.author == self.bot.user
        await ctx.channel.purge(check=is_bot, limit=1000)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    @commands.command()
    async def nr(self, ctx: Context) -> None: # nuke reactions
        async for msg in ctx.history():
            await msg.clear_reactions()

    @commands.command()
    async def how(self, ctx: Context) -> None:
        await ctx.send('magic')

class Sandwich(commands.Bot):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.db: cmyui.AsyncSQLPool
        self.http_sess: aiohttp.ClientSession

        self.cache = {'resp': {}} # many kinds

        self.add_cog(Commands(self))

    def run(self, token: str, *args, **kwargs) -> None:
        async def runner():
            self.db = cmyui.AsyncSQLPool()
            await self.db.connect(config.mysql)

            self.http_sess = aiohttp.ClientSession(json_serialize=orjson.dumps)

            try:
                await self.start(token, *args, **kwargs)
            except:
                await self.http_sess.close()
                await self.db.close()
                await self.close()

        loop = asyncio.get_event_loop()
        loop.create_task(runner())

        try:
            loop.run_forever()
        finally:
            pass

    async def process_commands(self, message: discord.Message) -> None:
        if message.author.bot:
            # don't process messages for bots
            return
        ctx = await self.get_context(message, cls=Context)
        await self.invoke(ctx)

    async def on_ready(self):
        log(f'{self.user} up', Ansi.LGREEN)

    async def on_message(self, msg: discord.Message) -> None:
        await self.process_commands(msg)

    async def on_message_edit(self, before: discord.Message,
                              after: discord.Message) -> None:
        await self.process_commands(after)

    async def on_message_delete(self, msg: discord.Message) -> None:
        if msg := self.cache['resp'].pop(msg.id, None):
            await msg.delete()

    async def on_command_error(self, ctx: Context,
                               error: commands.CommandError) -> None:
        if not isinstance(error, commands.errors.CommandNotFound): # ignore unknown cmds
            return await super().on_command_error(ctx, error)

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    bot = Sandwich(command_prefix='!', help_command=None)
    bot.run(config.discord_token)
