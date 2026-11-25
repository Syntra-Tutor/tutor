# Syntra Tutor

Pure CLI problem runner and Socratic systems-programming tutor.

Browser / WebAssembly / Neovim-plugin surfaces have been removed.
Edit and read solutions with plain vim (or `$VISUAL` / `$EDITOR`).

## Quick start

```bash
# install (editable) + symlink CLI
make install
# or: pip install -e . && ln -sf "$PWD/bin/tutor" ~/.local/bin/tutor

tutor list
tutor pick 002-hypervector-hamming   # scaffolds workspace and opens vim
tutor test 002-hypervector-hamming
```

## Editor

`tutor pick` opens the solution file with:

1. `$VISUAL` or `$EDITOR` if set  
2. `TUTOR_EDITOR` if set  
3. config key `editor`  
4. otherwise **`vim`**

Reading problem specs is the same path: the scaffolded workspace README and
solution are ordinary files; open them in vim.

## Remote compile (optional)

`tutor test --remote godbolt` still talks to Compiler Explorer over HTTPS
when a local compiler is unavailable. The old in-browser OSC "bridge" mode
is gone.

## Layout (CLI core)

```
tutor/          Python package (cli, runner, catalog, workspace, …)
bin/tutor       launcher
problems/       locked problem definitions + harnesses
policy/         architecture-as-code (OPA Rego)
tests/          unit tests
```

Write tests. Write theorems. Prove them. Bundle both.
