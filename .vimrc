call pathogen#infect()

:command WQ wq
:command Wq wq
:command W w
:command Q q

syntax enable

" https://github.com/fatih/vim-go.git
syntax enable  
filetype plugin on  
set number  
let g:go_disable_autoinstall = 0
let g:go_highlight_functions = 1  
let g:go_highlight_methods = 1  
let g:go_highlight_structs = 1  
let g:go_highlight_operators = 1  
let g:go_highlight_build_constraints = 1  

" github.com/Shougo/neocomplete.vim
let g:neocomplete#enable_at_startup = 1

map <C-n> :NERDTreeToggle<CR>
nmap <F8> :TagbarToggle<CR>

set background=light
let g:solarized_termcolors=256
"colorscheme solarized

colorscheme molokai
" Add highlighting for function definition in C++
function! EnhanceCppSyntax()
  syn match cppFuncDef "::\~\?\zs\h\w*\ze([^)]*\()\s*\(const\)\?\)\?$"
  hi def link cppFuncDef Special
endfunction
" set textwidth=79   lines longer than 79 columns will be broken
set shiftwidth=4  " operation >> indents 4 columns; << unindents 4 columns
set tabstop=4     " a hard TAB displays as 4 columns
set expandtab     " insert spaces when hitting TABs
set softtabstop=4 " insert/delete 4 spaces when hitting a TAB/BACKSPACE
set shiftround    " round indent to multiple of 'shiftwidth'
set autoindent    " align the new line indent with the previous line
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
set cindent
" Enable syntax highlighting
syntax on
" Allow mouse click
if has("mouse")
    set mouse=a
endif

let g:tagbar_type_go = {  
    \ 'ctagstype' : 'go',
    \ 'kinds'     : [
        \ 'p:package',
        \ 'i:imports:1',
        \ 'c:constants',
        \ 'v:variables',
        \ 't:types',
        \ 'n:interfaces',
        \ 'w:fields',
        \ 'e:embedded',
        \ 'm:methods',
        \ 'r:constructor',
        \ 'f:functions'
    \ ],
    \ 'sro' : '.',
    \ 'kind2scope' : {
        \ 't' : 'ctype',
        \ 'n' : 'ntype'
    \ },
    \ 'scope2kind' : {
        \ 'ctype' : 't',
        \ 'ntype' : 'n'
    \ },
    \ 'ctagsbin'  : 'gotags',
    \ 'ctagsargs' : '-sort -silent'
\ }
