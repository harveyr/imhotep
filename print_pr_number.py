import json
import sys


def main():
    try:
        branch = sys.argv[1]
    except KeyError:
        return print_usage_and_exit(1)

    try:
        data = json.load(sys.stdin)
    except ValueError:
        sys.exit('stdin could not be ')

    try:
        pr = next(p for p in data if p['head']['ref'] == branch)
    except StopIteration:
        sys.exit('No PR found for branch "{}"'.format(branch))

    print pr['number']


def print_usage_and_exit(exit_code=0):
    print 'usage:\n\tcat <prs.json> | python print_pr_number.py <branch>'
    print '\n<prs.json> must be a dump from the Github Pull Requests API'
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
