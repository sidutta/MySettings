syntax enable
set background=light
let g:solarized_termcolors=256
colorscheme solarized
" Python smart indent
autocmd BufRead *.py set smartindent cinwords=if,elif,else,for,while,try,except,finally,def,class
" Add highlighting for function definition in C++
function! EnhanceCppSyntax()
  syn match cppFuncDef "::\~\?\zs\h\w*\ze([^)]*\()\s*\(const\)\?\)\?$"
  hi def link cppFuncDef Special
endfunction
set tabstop=4
autocmd Syntax cpp call EnhanceCppSyntax()
" Use the OS clipboard by default (on versions compiled with `+clipboard`)
set clipboard=unnamed
" Show the filename in the window titlebar
set title
" Allow backspace in insert mode
set backspace=indent,eol,start
" Ignore case of searches
set ignorecase
" Highlight dynamically as pattern is typed
set incsearch
set pastetoggle=<F5>
map ˚ :cN
map ¬ :cn
map ˜ :w
map µ :make
map ∫ :wq
" C-like indentation
set autoindent
set cindent
" Enable syntax highlighting
syntax on
" Allow mouse click
if has("mouse")
    set mouse=a
endif
