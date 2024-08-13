# Repo-Downloader

Python CLI utility to download repositories from remote origins with autodetection, multibranch support and zipping. Very useful to create a general backup of yout projects.

## Roadmap
- [x] Bitbucket API support.
- [ ] Github API support.
- [ ] Gitlab API support.
- [ ] Enable multibranching.
- [ ] Zip all downloaded repositories.
    + [ ] ~~~~Create a zip by branch.
- [ ] Interactive shell options.
- [ ] Select skip projects.
- [ ] Multiplatform executable.
- [ ] GUI?

## Libraries
- GitPython
- requests


## Remotes
### Bitbucket
Allows to download all repos from an account. 

Needs to create an App Password at Bitbucket: https://bitbucket.org/account/settings/app-passwords/
Also, you need to create an ssh key.

### GitHub
TBD
