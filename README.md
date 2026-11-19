```
2026/11/19
Browser app has been phased out.
Use the CLI in conjunction with Synvim.

But a different browser implementation is being worked on.
First I tired bundling everything inside a browser vm,
but g++ compilation times in the vm were horrendously slow.

Solution? Compile clang to wasm.
Vim was already being compiled to wasm for the browser app.
Adding gdb and rr too.

Oh yeah I tried ttyd too but you know how that goes.
Needs to be set up outside the browser first; needless friction.
```



```
Yeah, so, the realization is, just fucking code. 
Write tests, and code.
Write theorems, then prove them.
Write declarative specifications, and check them.
And make sure you bundle both together.
```


