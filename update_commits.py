import argparse
import json
import subprocess
import sys


parser = argparse.ArgumentParser(prog=sys.argv[0], description='Update the commits for a given version to the latest HEAD')
parser.add_argument('--version', help="The version you would like to update")
args = vars(parser.parse_args())
with open("versions.json", "r") as v:
    versions = json.load(v)
    current_version = versions[args["version"]]
    updated = current_version.copy()
    for k, v in current_version.items():
        if "commit" in v:
            raise ValueError(f"The version \"{args['version']}\" already contains at least one commit information.")
        command = ["git", "ls-remote", v["repository"], f"refs/heads/{v['branch']}"]
        output = subprocess.check_output(command).decode('utf-8').strip()
        latest_commit_hash = output.split()[0]
        updated[k]["commit"] = latest_commit_hash
versions[args["version"]] = updated
with open("versions.json", "w") as result:
    result.write(json.dumps(versions, indent=2, sort_keys=True))






