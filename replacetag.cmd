# First arg is the branch
# Second arg is the version

git push origin --delete %1-%2
git tag -d %1-%2
git tag %1-%2 %1 -m "Version %2"
git push origin %1-%2
