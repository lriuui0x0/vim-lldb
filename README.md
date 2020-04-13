# Vim-LLDB

This is a LLDB debugger plugin for Neovim. It's currently in a very early stage, bug report would be much appreciated!

## Functionality

- Target selection
- Launch / step over / step in / step out / pause / resume / kill
- Breakpoint toggle / window
- Multi-thread stack window
- Watch window
    - View pointer as array using `pointer@length` or `pointer@offset,length` syntax
    - View register using `$rax` syntax

## Installation

- [`Neovim`](https://github.com/neovim/neovim) with python3 enabled, [`pynvim`](https://github.com/neovim/pynvim) installed
- LLDB wth python3 package enabled, you may need to compile LLDB from source with the following `cmake` arguments:
    - `-DLLDB_ENABLE_PYTHON=1`
    - `-DPYTHON_LIBRARY=<path to python3 dynamic-link library>`
    - `-DPYTHON_INCLUDE_DIR=<path to the directory containing Python.h>`
- Install this plugin with your vim plugin manager, you need to run `:UpdateRemotePlugins` after the plugin is installed
    - If you use [`vim-plug`](https://github.com/junegunn/vim-plug), you can use single line
        ```
        Plug 'lriuui0x0/vim-lldb', { 'do': ':UpdateRemotePlugins' }
        ```

## Usage

Below is the list of functions available:

- `VimLLDB_SelectTarget(index | name)`

    Select target defined in the variable `g:vim_lldb_targets`. `g:vim_lldb_targets` is a list of dictionary, each has 5 mandatory keys:
    - `name`: The name of target used for selection, string
    - `executable`: The local binary to debug, string
    - `arguments`: The arguments passed to the binary, list of string
    - `working_dir`: The working directory, string
    - `environments`: The environment variables, list of string in the format of `KEY=VALUE`

    This function automatically reloads the target definitions. You can select target by index or by name.

    When vim starts, if will automatically select the first target.

- `VimLLDB_ToggleDebugger()`

    Toggle the debugger view, which includes a stack window, watch window, and a breakpoint window.

- `VimLLDB_Launch()`

    Launch the selected target.

- `VimLLDB_StepOver()`

    Step over the process.

- `VimLLDB_StepInto()`

    Step into the current function.

- `VimLLDB_StepOut()`

    Step out the current function.

- `VimLLDB_Resume()`

    Resume the stopped process.

- `VimLLDB_Pause()`

    Pause the running process.

- `VimLLDB_Kill()`

    Kill the launched process.

- `VimLLDB_ToggleBreakpoint()`

    Toggle the breakpoint on the current line.

I use the following key mappings to save typing functions. You can copy and modify:

```vim
nnoremap <A-q> :call VimLLDB_ToggleDebugger()<CR>
nnoremap <A-x> :call VimLLDB_Launch()<CR>
nnoremap <A-z> :call VimLLDB_Kill()<CR>
nnoremap <A-c> :call VimLLDB_Resume()<CR>
nnoremap <A-v> :call VimLLDB_Stop()<CR>
nnoremap <A-b> :call VimLLDB_ToggleBreakpoint()<CR>
nnoremap <A-n> :call VimLLDB_StepOver()<CR>
nnoremap <A-m> :call VimLLDB_StepInto()<CR>
nnoremap <A-,> :call VimLLDB_StepOut()<CR>

```

---

Within each debugger window, there're key mappings (currently non-configurable) defined below:

- Stack window
    - `<CR>` Goto the frame source code.

    - `<C-n>` See next thread stack.

    - `<C-p>` See previous thread stack.

- Breakpoint window
    - `<CR>` Goto the breakpoint location.

    - `md` Remove breakpoint.

- Watch window
    - `ma` Add watch expression.

    - `mm` Modify watch expression.
        
    - `md` Remove watch expression.

    - `o` Expand watch value.

    - `x` Collapse watch value.

