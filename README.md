## Create a release
To create a release, define the version and its submodules inside the version.json. Run the "update_commits.py" with the attribute "--version X" which then updates the commit information to the current head of the configured submodule branches. Existing commit hashes for this version will be replaced.

### version.json
The version.json defines the submodule versions which are composing an openMINDS release.


Versions defined without commit hash are supposed to point to head of the corresponding branch. If no branch is defined, this means that the latest commit on the **semantically highest version branch** is taken into account.