#!/usr/bin/python3.9
# -*- coding: utf-8 -*-

import asyncio
import aiohttp

import orjson
import cmyui
from cmyui import log, Ansi
import traceback
import random
from typing import Any, Optional
from collections import namedtuple
from pathlib import Path

import discord
from discord.ext import commands

import config

# what is this lol
NO = tuple([
    'thou may not take thy toothpick',
    'no',
] + [
    f'u may not taste my delicious {x}' for x in [
        'tomatoes', 'lettuce', 'ham', 'chicken', 'cheese',
        'mayonaise', 'pickles', 'pumpernickel'
    ]
])

#def read_list(b: bytes, chunk_size: int = 4) -> list[int]:
#    if not (length := int.from_bytes(b[:2], 'little')):
#        return []
#
#    l = []
#    for i in range(length):
#        l.append(int.from_bytes(b[i:i+chunk_size], 'little'))
#
#    return l
#
#def write_list(l: list[int], chunk_size: int = 4) -> bytes:
#    if not l:
#        return b'\x00\x00'
#
#    b = bytearray(len(l).to_bytes(2, 'little'))
#    for i in l:
#        b += i.to_bytes(chunk_size, 'little')
#    return bytes(b)
#
#def multi_map(l, F, *Fs) -> Any:
#    return map((l, F, *Fs) if Fs else (l, F))

class Context(commands.Context):
    async def send(self, content = None, new = False, **kwargs) -> Optional[discord.Message]:
        # `new` is an override to the cache
        if not new and self.message.id in self.bot.cache['resp']:
            msg = self.bot.cache['resp'][self.message.id]
            content = content or msg.content
            embed = kwargs.get('embed', None)
            await msg.edit(content=content, embed=embed)
        else:
            msg = await super().send(content, **kwargs)
            self.bot.cache['resp'][self.message.id] = msg

        return msg

# used for saving values in `Commands().namespace` from !py land
SavedValue = namedtuple('SavedValue', ['name', 'value'])

def _save(k: str, v: Any) -> SavedValue:
    return SavedValue(k, v)

def _saved(g: dict[str, Any]) -> dict[str, Any]:
    return {k: g[k] for k in set(g) - {'__builtins__', '__py'}}

class Commands(commands.Cog):
    def __init__(self, bot: 'BotPP') -> None:
        self.bot = bot
        self.whitelist = {
            285190493703503872, # cmyui
            343508538246561796, # cover
            347459855449325570, # flame
            455300278120480770, # cherry
        }

        self.namespace = {'save': _save, 'saved': _saved}

        # add commonly used modules to namespace
        for mod in ('asyncio', 'os', 'sys', 'struct',
                    'discord', 'cmyui', 'datetime',
                    'time', 'inspect'):
            self.namespace[mod] = __import__(mod)

    @commands.is_owner()
    @commands.command()
    async def addwl(self, ctx: Context):
        self.whitelist |= set(m.id for m in ctx.message.mentions)
        await ctx.send('Yep')

    @commands.is_owner()
    @commands.command()
    async def rmwl(self, ctx: Context):
        self.whitelist -= set(m.id for m in ctx.message.mentions)
        await ctx.send('Yep')

    @commands.command()
    async def cpp(self, ctx: Context) -> None:
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
            #    await ctx.send(f'```cpp\n{stderr[part:part+1990]}```', new=True)
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
        if f_text.startswith('py\n'):
            f_text = f_text[3:]
        elif f_text.startswith('python\n'):
            f_text = f_text[7:]

        f_def = f'async def __py(ctx):\n{f_text}'.replace('\n', '\n ')

        try:
            exec(f_def, self.namespace) # def __py(ctx)
            __py = self.namespace['__py']
            ret = await __py(ctx)
        except:
            await ctx.send(f'```py\n{traceback.format_exc()}```')
            return

        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

        if ret is None:
            return

        if isinstance(ret, SavedValue):
            if ret.name in self.namespace:
                await ctx.send(f'Would shadow `{ret.name}` - please delete it first!')
            else:
                self.namespace |= {ret.name: ret.value}
                await ctx.send(f'Added `{ret.name}` to namespace.')
        else:
            #for part in map(''.join, zip_longest(*[iter(str(ret))]*2000, fillvalue='')):
            #    await ctx.send(part, new=True)

            ret = str(ret)
            if len(ret) > 2000:
                ret = f'{ret[:1997]}...'

            await ctx.send(ret)

    @commands.command()
    async def nukeself(self, ctx: Context):
        await ctx.channel.purge(check=lambda m: m.author == self.bot.user, limit=1000)
        await ctx.send('done')

    @commands.command()
    async def how(self, ctx: Context) -> None:
        await ctx.send('magic')

class BotPP(commands.Bot):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        #self.db: cmyui.AsyncSQLPool
        self.http_sess: aiohttp.ClientSession

        self.cache = {'resp': {}} # many kinds

        self.add_cog(Commands(self))

    def run(self, token: str, *args, **kwargs) -> None:
        async def runner():
            #self.db = cmyui.AsyncSQLPool()
            #await self.db.connect(config.mysql)

            self.http_sess = aiohttp.ClientSession(json_serialize=orjson.dumps)

            try:
                await self.start(token, *args, **kwargs)
            except:
                await self.http_sess.close()
                #await self.db.close()
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

if __name__ == '__main__':
    bot = BotPP(command_prefix='!', help_command=None)
    bot.run(config.discord_token)
