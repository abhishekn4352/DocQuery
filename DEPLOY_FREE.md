# Deploying DocQuery for Free

Two options, both genuinely free (no card, no trial that expires). Try
**Render** first — it's less setup. If it crashes right after starting
(not during the build), that's almost certainly its 512MB RAM limit being
too tight for the embedding model + PyTorch — switch to **Hugging Face
Spaces**, which gives 16GB free.

**The one trade-off on both, upfront:** free tiers reset their disk when
the app sleeps from inactivity and wakes back up. Uploaded documents, the
vector index, and chat history won't survive a long idle period. For a
demo link people try in one sitting, you won't notice this. If you need
uploads to actually stick around long-term for free, that needs a small
code change to point storage at a free external database instead of the
local disk — ask if you want that.

---

## Option 1: Render (try this first)

1. **Push this project to a GitHub repo** if it isn't already there:
   ```bash
   git init
   git add .
   git commit -m "deploy"
   git branch -M main
   git remote add origin <your-repo-url>
   git push -u origin main
   ```
2. Sign up at **render.com** with GitHub. No credit card needed for Free.
3. **New +** → **Web Service** → pick your repo.
4. Settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python -m backend.main`
   - Instance Type: **Free**
5. Add environment variables:
   - `GROQ_API_KEY` = your key
   - `HOST` = `0.0.0.0`
   - `RELOAD` = `false`
   - (leave `PORT` unset — Render sets it automatically and the app already reads it)
6. **Create Web Service**. First build takes a few minutes. Once it says
   "Live", your app is at `https://<your-service-name>.onrender.com`.

If it builds fine but the app dies right after "Starting service" in the
logs, that's the RAM ceiling — go to Option 2.

---

## Option 2: Hugging Face Spaces (16GB free RAM, needs Docker)

This project already includes `Dockerfile` and `.dockerignore` for this —
you don't need to write anything.

1. Create a free account at **huggingface.co/join**.
2. Go to **huggingface.co/new-space**:
   - Space name: your choice
   - License: your choice
   - **SDK: Docker** (important — not Gradio/Streamlit)
   - Hardware: **CPU basic · Free**
   - Visibility: Public or Private, your choice
3. HF gives you a new git repo for the Space. Clone it, copy this
   project's files into it (including the `Dockerfile` and
   `.dockerignore`), then push:
   ```bash
   git clone https://huggingface.co/spaces/<your-username>/<your-space-name>
   # copy DocQuery's files into that cloned folder, then:
   cd <your-space-name>
   git add .
   git commit -m "deploy DocQuery"
   git push
   ```
4. At the very top of that repo's `README.md`, above everything else,
   add this block (HF reads it to configure the Space — without it the
   Space won't know to use Docker):
   ```yaml
   ---
   title: DocQuery
   emoji: 📄
   colorFrom: blue
   colorTo: indigo
   sdk: docker
   app_port: 7860
   pinned: false
   ---
   ```
5. In the Space, go to **Settings → Variables and secrets → New secret**
   and add `GROQ_API_KEY` there (as a *secret*, not a variable — a
   variable would be visible in public build logs). Don't put the key in
   any file you commit.
6. The Space builds automatically after the push. Watch the **Logs** tab.
   Once it says "Running", your app is at
   `https://<your-username>-<your-space-name>.hf.space`.

**Honest note on this Dockerfile:** I wrote and reasoned through it
carefully — correct port (7860, what Spaces' Docker SDK expects), correct
non-root user setup, `HOST=0.0.0.0`, cache directory that's actually
writable — but this sandbox has no Docker daemon, so I couldn't literally
build and run the image myself the way I tested the rest of this project.
Everything in it follows Hugging Face's own documented pattern, but watch
the build logs on the first push in case any one dependency needs
something the base image doesn't have.
