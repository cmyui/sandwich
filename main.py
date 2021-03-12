#!/usr/bin/python3.9
# -*- coding: utf-8 -*-

"""my personal (messy) discord bot. made (and great) for functionality."""

import asyncio
import random
from collections import namedtuple
import traceback
from typing import Optional
from pathlib import Path
from typing import Any

import aiohttp
import cmyui

import discord
import orjson
from cmyui import Ansi
from cmyui import log
from discord.ext import commands

import config

# what is this lol
NO = tuple([
    'thou may not take thy toothpick',
    'no',
    'yo m',
] + [
    f'u may not taste my delicious {x}' for x in [
        'tomatoes', 'lettuce', 'ham', 'chicken', 'cheese',
        'mayonaise', 'pickles', 'pumpernickel'
    ]
])

class Context(commands.Context):
    async def send(self, content = None, force_new = False,
                   **kwargs) -> Optional[discord.Message]:
        bot_msg: discord.Message

        if force_new or self.message.id in self.bot.cache['resp']:
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
        else:
            bot_msg = await super().send(content, **kwargs)
            self.bot.cache['resp'][self.message.id] = bot_msg

        return bot_msg

# used for saving values in `Commands().namespace` from !py land
SavedValue = namedtuple('SavedValue', ['name', 'value'])

def _save(k: str, v: Any) -> SavedValue:
    return SavedValue(k, v)

def _saved(g: dict[str, Any]) -> dict[str, Any]:
    return {k: g[k] for k in set(g) - {'__builtins__', '__py'}}

class Commands(commands.Cog):
    def __init__(self, bot: 'Sandwich') -> None:
        self.bot = bot

        # some people allowed to use dangerous
        # commands by default, this would be a
        # security risk on a 'real' bot.
        self.whitelist = {
            285190493703503872, # cmyui
            343508538246561796, # cover
            347459855449325570, # flame
            455300278120480770, # cherry
        }

        # a dict for our global variables within the !py command.
        # by default, this has functions to save vars, retrieve saved ones,
        self.namespace = {'save': _save, 'saved': _saved}

        # and also contains frequently used modules for ease of access.
        for mod_name in (
            'asyncio', 'os', 'sys', 'struct',
            'discord', 'cmyui', 'datetime',
            'time', 'inspect', 'math',
            'pickle', 'dill'
        ):
            self.namespace[mod_name] = __import__(mod_name)

    @commands.is_owner()
    @commands.command()
    async def addwl(self, ctx: Context):
        self.whitelist |= set(m.id for m in ctx.message.mentions)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    @commands.is_owner()
    @commands.command()
    async def rmwl(self, ctx: Context):
        self.whitelist -= set(m.id for m in ctx.message.mentions)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    @commands.command()
    async def cpp(self, ctx: Context) -> None:
        """Compile message with gcc as c++17 & run it, returning stdout."""
        if ctx.author.id not in self.whitelist:
            return await ctx.send(random.choice(NO))

        content = ctx.message.content
        cmd = '{prefix}{invoked_with}'.format(**ctx.__dict__)

        if content == cmd:
            await ctx.send('owo')
            return

        cpp_text = content.removeprefix(cmd)[1:]

        # create file with the code
        cpp_file = Path.cwd() / '_temp.cpp'
        bin_file = Path.cwd() / '_temp.o'
        cpp_file.write_text(cpp_text)

        PIPE = asyncio.subprocess.PIPE
        #DEVNULL = asyncio.subprocess.DEVNULL

        # run gcc compiler in subproc on it
        # TODO: this doesn't work on uvloop? lol
        proc = await asyncio.subprocess.create_subprocess_exec(
            'g++', '_temp.cpp', '-std=c++17',
            '-o', '_temp.o', '-Wall',
            stdout=PIPE, stderr=PIPE
        )

        _, stderr = [x.decode() for x in await proc.communicate()]

        if stderr:
            # warning/errors
            await ctx.send(f'```cpp\n{stderr[:1987]}...```')
            #for part in range(0, len(stderr), 1990):
            #    await ctx.send(f'```cpp\n{stderr[part:part+1990]}```', force_new=True)
            if not bin_file.exists():
                # compilation failed (errors).
                return

        # run the program in subproc
        proc = await asyncio.subprocess.create_subprocess_exec(
            './_temp.o', stdout=PIPE, stderr=PIPE
        )

        stdout, stderr = [x.decode() for x in await proc.communicate()]

        # remove temp files
        cpp_file.unlink()
        bin_file.unlink()

        if out := stdout or stderr:
            try:
                await ctx.send(out)
            except:
                await ctx.send(traceback.format_exc())
        #else:
        #    await ctx.send('Success.')

        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    @commands.command()
    async def py(self, ctx: Context) -> None:
        """Parse & execute message via python interpreter."""
        if ctx.author.id not in self.whitelist:
            return await ctx.send(random.choice(NO))

        content = ctx.message.content
        cmd = '{prefix}{invoked_with}'.format(**ctx.__dict__)

        if content == cmd:
            await ctx.send('owo')
            return

        # remove the command's invocation prefix and strip any
        # newlines, ticks, and spaces from both ends of the text.
        f_text = content.removeprefix(cmd).strip('`\n ')

        # replace long sequences of newlines with single ones.
        f_text = '\n'.join(s for s in f_text.split('\n') if s)

        # remove any discord embed skinning.
        for prefix in ('py', 'python'):
            f_text = f_text.removeprefix(f'{prefix}\n')

        f_text = f' {f_text}'.replace('\n', '\n ') # indent
        f_def = f'async def __py(ctx):\n{f_text}'

        try:
            exec(f_def, self.namespace)             # compile function
            ret = await self.namespace['__py'](ctx) # await it's return
        except:
            """
            # !py failed to compile, or run, get the exception lines.
            # [2:] to remove useless lines, [:-1] to remove newlines.
            tb_lines = [l[:-1] for l in traceback.format_exception(
                *sys.exc_info(), limit = None, chain = True
            )[2:]]

            '  File "<string>", line 8, in __py'
            # format the exception output for our (strange) use case.
            line_num = int(tb_lines.pop(0)[23:]) - 1 # err line num
            err_line = tb_lines.pop(-1) # err msg
            tb_msg = '\n'.join([l[4:] for l in tb_lines]) # dedent

            # send back tb in discord chat.
            await ctx.send(f'**{err_line}** @ L{line_num} ```py\n{tb_msg}```')
            """
            await ctx.send(f'```{traceback.format_exc()}```')
            await ctx.message.add_reaction('\N{CROSS MARK}')
            return
        else:
            # !py ran successfully.
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

        if ret is None:
            # clear any previous responses
            await ctx.send(None)
            return

        # the return value may be from the !save command.
        if isinstance(ret, SavedValue):
            # NOTE: this will overwrite preexisting vars.
            self.namespace |= {ret.name: ret.value}
            await ctx.send(f'Added `{ret.name}` to namespace.')
        else:
            ret = str(ret)

            # discord content len limited to 2k chars.
            if len(ret) > 2000:
                ret = f'{ret[:1989]}... (trunc)'

            await ctx.send(ret)

    @commands.command()
    async def nukeself(self, ctx: Context):
        is_bot = lambda m: m.author == self.bot.user
        await ctx.channel.purge(check=is_bot, limit=1000)
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    @commands.command()
    async def how(self, ctx: Context) -> None:
        await ctx.send('magic')

    @commands.command()
    async def nr(self, ctx: Context) -> None:
        async for msg in ctx.history():
            await msg.clear_reactions()

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
            return super().on_command_error(ctx, error)

if __name__ == '__main__':
    bot = Sandwich(command_prefix='!', help_command=None)
    bot.run(config.discord_token)
