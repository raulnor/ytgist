import argparse
import sys

from ytgist import db, transcript, web


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ytgist")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("get-transcript", help="Fetch a transcript",
                    add_help=False).set_defaults(run=transcript.main)
    sub.add_parser("logs", help="Return db path",
                    add_help=False).set_defaults(run=lambda _: print(db.db_path()))
    sub.add_parser("web", help="Run the web UI",
                    add_help=False).set_defaults(run=web.main)

    # Parse only the first arg to route; let the subcommand parse the rest
    args, rest = parser.parse_known_args(argv)
    return args.run(rest)


if __name__ == "__main__":
    sys.exit(main())