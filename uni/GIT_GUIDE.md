# Git Guide for the Team

Five people, one repo, one rule: **nobody pushes to `main`**. You work on your own branch and merge through a Pull Request (PR).

## One-time setup (everyone)

```bash
git config --global user.name  "Your Name"
git config --global user.email "your-github-email@example.com"
```
Use your own name and email: contribution is judged by commits under your name.

## One-time setup (repo owner only)

1. GitHub → New repository → `uni-chatbot` → keep it empty (no README, we already have one).
2. From the project folder:
```bash
git init
git add .
git commit -m "Initial project structure"
git branch -M main
git remote add origin https://github.com/<you>/uni-chatbot.git
git push -u origin main
```
3. Settings → Collaborators → invite the 4 teammates.
4. Settings → Branches → Add rule for `main` → require a pull request before merging (1 approval).

## 1. Clone (once)

```bash
git clone https://github.com/<you>/uni-chatbot.git
cd uni-chatbot
cp .env.example .env
```

## 2. Weekly loop

```bash
git checkout main
git pull                      # get everyone's latest work
git checkout -b m1/w1         # your branch: <member>/<week>
```

Work on your files, then save often:
```bash
git status                    # what changed?
git add backend/app/core/config.py
git commit -m "Add config with get_today override"
```

Push your branch:
```bash
git push -u origin m1/w1      # first time
git push                      # later pushes
```

## 3. Open a Pull Request

1. On GitHub, click **Compare & pull request**.
2. Fill the template, tag a reviewer.
3. The reviewer approves (or comments), then you click **Merge**.
4. Everyone pulls:
```bash
git checkout main
git pull
```

## 4. Stay up to date while you work

Teammates merge things you need (for example M1's `shared_models.py`). Bring them into your branch:
```bash
git checkout main
git pull
git checkout m2/w1
git merge main
```

## 5. Fixing a merge conflict

A conflict means two people edited the same lines. Git marks them:
```
<<<<<<< HEAD
your version
=======
their version
>>>>>>> main
```
1. Open the file, keep the right lines, delete the markers.
2. `git add <file>` then `git commit`.
3. Not sure which is right? Ask the other person.

Most conflicts are avoided because each person owns different files.

## Commit message style

Short and clear, present tense: `Add prereq check`, `Fix seat count race`, `Update golden questions`.

## Cheat sheet

| I want to... | Command |
|---|---|
| See what changed | `git status` |
| See my branches | `git branch` |
| Switch branch | `git checkout <name>` |
| Undo an unstaged edit | `git restore <file>` |
| See history | `git log --oneline` |
| Get latest main | `git checkout main && git pull` |

## Never

- Push to `main` directly.
- Commit `.env`, keys or passwords. If it happens, tell the team right away and change the key.
- Use `git push --force`.

---

# Demo script for teammates (about 15 min)

Share your screen. Everyone has Git installed and is a collaborator on the repo.

| Min | Step | What to show |
|---|---|---|
| 0-2 | **The idea** | Open the repo on GitHub. Explain: `main` is the safe shared version; branches are your own copy to work on; a PR is how work gets merged. Show the folder layout and the README. |
| 2-4 | **Clone** | Everyone runs `git clone <url>` and `cd uni-chatbot`. Open it in VS Code. |
| 4-6 | **Branch** | `git checkout -b <member>/demo` (for example `m3/demo`). Run `git branch` to show you're on it. |
| 6-8 | **Change + commit** | Create `docs/team/<yourname>.md` with one line about you. `git status`, `git add`, `git commit -m "Add <name> to team page"`. |
| 8-10 | **Push** | `git push -u origin <member>/demo`. Refresh GitHub and show the new branch. |
| 10-12 | **Pull Request** | Click Compare & pull request, open it, tag a teammate. One person reviews and merges. |
| 12-13 | **Pull** | Everyone runs `git checkout main && git pull` and sees the merged files appear. |
| 13-15 | **Conflict (on purpose)** | Two people edit the same line of `docs/team/demo.md` on different branches, merge one, then try merging the other. Resolve it together as in section 5. |

Finish by deleting the demo files in a small PR, and agree on the weekly branch names (`m1/w1`, `m2/w1`, ...).
