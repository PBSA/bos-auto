#!/usr/bin/env python3

import click
from rq import Connection, Worker, use_connection, Queue
from .config import loadConfig
import logging
log = logging.getLogger()

config = loadConfig()


@click.group()
def main():
    """ Main group for python-click so we can offer subcommands in a single cli
        tool
    """
    pass


@main.command()
@click.option(
    "--port",
    type=int,
    default=8010
)
@click.option(
    "--host",
    type=str,
    default="127.0.0.1"
)
@click.option(
    "--host",
    type=str,
    default="127.0.0.1"
)
@click.option(
    '--debug',
    is_flag=True,
    default=False
)
@click.option(
    "--proposer"
)
@click.option(
    "--approver"
)
def api(port, host, debug, proposer, approver):
    """ Start the API endpoint
    """
    from bookied.web import app
    app.config["BOOKIE_PROPOSER"] = proposer
    app.config["BOOKIE_APPROVER"] = approver
    app.run(
        host=host,
        port=port,
        debug=debug
    )


@main.command()
@click.argument("queue", default="default")
def worker(queue):
    """ Start the (redis queue) worker to deal with the received messages
    """
    from .redis_con import redis
    with Connection(redis):
        w = Worker([queue])
        w.work()


@main.command()
@click.option(
    "--proposer",
    default=config.get("BOOKIE_PROPOSER")
)
@click.option(
    "--approver",
    default=config.get("BOOKIE_APPROVER")
)
def approve(proposer, approver):
    from .redis_con import redis
    from . import work
    use_connection(redis)
    q = Queue(connection=redis)
    q.enqueue(
        work.approve,
        args=(),
        kwargs=dict(
            proposer=proposer,
            approver=approver
        )
    )


@main.command()
@click.argument(
    "filename",
    type=click.File('rb'))
@click.option(
    "--proposer",
    default=config.get("BOOKIE_PROPOSER")
)
@click.option(
    "--approver",
    default=config.get("BOOKIE_APPROVER")
)
@click.option(
    "--call",
    default=None,
    type=click.Choice([
            "in_progress",
            "create",
            "finish",
            "result"])
)
@click.option(
    "--dry-run/--no-dry-run",
    default=False)
@click.option(
    "--url",
    default="http://localhost:8010/trigger"
)
def replay(filename, proposer, approver, url, call, dry_run):
    from tqdm import tqdm
    from pprint import pprint
    import json
    import requests
    for line in tqdm(filename.readlines()):
        data = eval(line)
        data.update(dict(approver=approver, proposer=proposer))
        if data["call"] != call:
            continue

        # Filter by "call"
        if call and call.lower() != data["call"]:
            continue

        # Print
        pprint(data)

        # Request
        if dry_run:
            continue

        try:
            requests.post(
                url,
                json=data,
                headers={'Content-Type': 'application/json'}
            )
        except:
            log.error("[Error] Failed pushing")


if __name__ == "__main__":
    main()
