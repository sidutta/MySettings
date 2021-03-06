# Copyright (c) 2003-2013 LOGILAB S.A. (Paris, FRANCE).
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
"""Python code format's checker.

By default try to follow Guido's style guide :

http://www.python.org/doc/essays/styleguide.html

Some parts of the process_token method is based from The Tab Nanny std module.
"""

import keyword
import sys
import tokenize

if not hasattr(tokenize, 'NL'):
    raise ValueError("tokenize.NL doesn't exist -- tokenize module too old")

from astroid import nodes

from pylint.interfaces import ITokenChecker, IAstroidChecker, IRawChecker
from pylint.checkers import BaseTokenChecker
from pylint.checkers.utils import check_messages
from pylint.utils import WarningScope, OPTION_RGX

_CONTINUATION_BLOCK_OPENERS = ['elif', 'except', 'for', 'if', 'while', 'def', 'class']
_KEYWORD_TOKENS = ['assert', 'del', 'elif', 'except', 'for', 'if', 'in', 'not',
                   'raise', 'return', 'while', 'yield']
if sys.version_info < (3, 0):
    _KEYWORD_TOKENS.append('print')

_SPACED_OPERATORS = ['==', '<', '>', '!=', '<>', '<=', '>=',
                     '+=', '-=', '*=', '**=', '/=', '//=', '&=', '|=', '^=',
                     '%=', '>>=', '<<=']
_OPENING_BRACKETS = ['(', '[', '{']
_CLOSING_BRACKETS = [')', ']', '}']
_TAB_LENGTH = 8

_EOL = frozenset([tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT])
_JUNK_TOKENS = (tokenize.COMMENT, tokenize.NL)

# Whitespace checking policy constants
_MUST = 0
_MUST_NOT = 1
_IGNORE = 2

# Whitespace checking config constants
_DICT_SEPARATOR = 'dict-separator'
_TRAILING_COMMA = 'trailing-comma'
_NO_SPACE_CHECK_CHOICES = [_TRAILING_COMMA, _DICT_SEPARATOR]

MSGS = {
    'C0301': ('Line too long (%s/%s)',
              'line-too-long',
              'Used when a line is longer than a given number of characters.'),
    'C0302': ('Too many lines in module (%s)', # was W0302
              'too-many-lines',
              'Used when a module has too much lines, reducing its readability.'
              ),
    'C0303': ('Trailing whitespace',
              'trailing-whitespace',
              'Used when there is whitespace between the end of a line and the '
              'newline.'),
    'C0304': ('Final newline missing',
              'missing-final-newline',
              'Used when the last line in a file is missing a newline.'),
    'W0311': ('Bad indentation. Found %s %s, expected %s',
              'bad-indentation',
              'Used when an unexpected number of indentation\'s tabulations or '
              'spaces has been found.'),
    'C0330': ('Wrong %s indentation%s.\n%s%s',
              'bad-continuation',
              'TODO'),
    'W0312': ('Found indentation with %ss instead of %ss',
              'mixed-indentation',
              'Used when there are some mixed tabs and spaces in a module.'),
    'W0301': ('Unnecessary semicolon', # was W0106
              'unnecessary-semicolon',
              'Used when a statement is ended by a semi-colon (";"), which \
              isn\'t necessary (that\'s python, not C ;).'),
    'C0321': ('More than one statement on a single line',
              'multiple-statements',
              'Used when more than on statement are found on the same line.',
              {'scope': WarningScope.NODE}),
    'C0325' : ('Unnecessary parens after %r keyword',
               'superfluous-parens',
               'Used when a single item in parentheses follows an if, for, or '
               'other keyword.'),
    'C0326': ('%s space %s %s %s\n%s',
              'bad-whitespace',
              ('Used when a wrong number of spaces is used around an operator, '
               'bracket or block opener.'),
              {'old_names': [('C0323', 'no-space-after-operator'),
                             ('C0324', 'no-space-after-comma'),
                             ('C0322', 'no-space-before-operator')]})
    }


if sys.version_info < (3, 0):

    MSGS.update({
    'W0331': ('Use of the <> operator',
              'old-ne-operator',
              'Used when the deprecated "<>" operator is used instead \
              of "!=".'),
    'W0332': ('Use of "l" as long integer identifier',
              'lowercase-l-suffix',
              'Used when a lower case "l" is used to mark a long integer. You '
              'should use a upper case "L" since the letter "l" looks too much '
              'like the digit "1"'),
    'W0333': ('Use of the `` operator',
              'backtick',
              'Used when the deprecated "``" (backtick) operator is used '
              'instead  of the str() function.',
              {'scope': WarningScope.NODE}),
    })


def _underline_token(token):
    length = token[3][1] - token[2][1]
    offset = token[2][1]
    return token[4] + (' ' * offset) + ('^' * length)


def _column_distance(token1, token2):
    if token1 == token2:
        return 0
    if token2[3] < token1[3]:
        token1, token2 = token2, token1
    if token1[3][0] != token2[2][0]:
        return None
    return token2[2][1] - token1[3][1]


def _last_token_on_line_is(tokens, line_end, token):
    return (
        line_end > 0 and tokens.token(line_end-1) == token or
        line_end > 1 and tokens.token(line_end-2) == token 
        and tokens.type(line_end-1) == tokenize.COMMENT)


def _token_followed_by_eol(tokens, position):
  return (tokens.type(position+1) == tokenize.NL or
          tokens.type(position+1) == tokenize.COMMENT and
          tokens.type(position+2) == tokenize.NL)


def _get_indent_length(line):
  """Return the length of the indentation on the given token's line."""
  result = 0
  for char in line:
    if char == ' ':
      result += 1
    elif char == '\t':
      result += _TAB_LENGTH
    else:
      break
  return result


def _get_indent_hint_line(bar_positions, bad_position):
    """Return a line with |s for each of the positions in the given lists."""
    if not bar_positions:
        return ''
    markers = [(pos, '|') for pos in bar_positions]
    markers.append((bad_position, '^'))
    markers.sort()
    line = [' '] * (markers[-1][0] + 1)
    for position, marker in markers:
        line[position] = marker
    return ''.join(line)


class _ContinuedIndent(object):
    __slots__ = ('valid_outdent_offsets',
                 'valid_continuation_offsets',
                 'context_type',
                 'token',
                 'position')

    def __init__(self,
                 context_type,
                 token,
                 position,
                 valid_outdent_offsets,
                 valid_continuation_offsets):
        self.valid_outdent_offsets = valid_outdent_offsets
        self.valid_continuation_offsets = valid_continuation_offsets
        self.context_type = context_type
        self.position = position
        self.token = token


# The contexts for hanging indents.
# A hanging indented dictionary value after :
HANGING_DICT_VALUE = 'dict-value'
# Hanging indentation in an expression.
HANGING = 'hanging'
# Hanging indentation in a block header.
HANGING_BLOCK = 'hanging-block'
# Continued indentation inside an expression.
CONTINUED = 'continued'
# Continued indentation in a block header.
CONTINUED_BLOCK = 'continued-block'

SINGLE_LINE = 'single'
WITH_BODY = 'multi'

_CONTINUATION_MSG_PARTS = {
    HANGING_DICT_VALUE: ('hanging', ' in dict value'),
    HANGING: ('hanging', ''),
    HANGING_BLOCK: ('hanging', ' before block'),
    CONTINUED: ('continued', ''),
    CONTINUED_BLOCK: ('continued', ' before block'),
}


def _Offsets(*args):
    """Valid indentation offsets for a continued line."""
    return dict((a, None) for a in args)


def _BeforeBlockOffsets(single, with_body):
    """Valid alternative indent offsets for continued lines before blocks.

    :param single: Valid offset for statements on a single logical line.
    :param with_body: Valid offset for statements on several lines.
    """
    return {single: SINGLE_LINE, with_body: WITH_BODY}


class TokenWrapper(object):
    """A wrapper for readable access to token information."""

    def __init__(self, tokens):
        self._tokens = tokens

    def token(self, idx):
        return self._tokens[idx][1]

    def type(self, idx):
        return self._tokens[idx][0]

    def start_line(self, idx):
        return self._tokens[idx][2][0]

    def start_col(self, idx):
        return self._tokens[idx][2][1]

    def line(self, idx):
        return self._tokens[idx][4]


class ContinuedLineState(object):
    """Tracker for continued indentation inside a logical line."""

    def __init__(self, tokens, config):
        self._line_start = -1
        self._cont_stack = []
        self._is_block_opener = False
        self.retained_warnings = []
        self._config = config
        self._tokens = TokenWrapper(tokens)

    @property
    def has_content(self):
        return bool(self._cont_stack)

    @property
    def _block_indent_size(self):
        return len(self._config.indent_string.replace('\t', ' ' * _TAB_LENGTH))

    @property
    def _continuation_size(self):
        return self._config.indent_after_paren

    def handle_line_start(self, pos):
        """Record the first non-junk token at the start of a line."""
        if self._line_start > -1:
            return
        self._is_block_opener = self._tokens.token(pos) in _CONTINUATION_BLOCK_OPENERS
        self._line_start = pos

    def next_physical_line(self):
        """Prepares the tracker for a new physical line (NL)."""
        self._line_start = -1
        self._is_block_opener = False

    def next_logical_line(self):
        """Prepares the tracker for a new logical line (NEWLINE).

        A new logical line only starts with block indentation.
        """
        self.next_physical_line()
        self.retained_warnings = []
        self._cont_stack = []

    def add_block_warning(self, token_position, state, valid_offsets):
        self.retained_warnings.append((token_position, state, valid_offsets))

    def get_valid_offsets(self, idx):
        """"Returns the valid offsets for the token at the given position."""
        # The closing brace on a dict or the 'for' in a dict comprehension may
        # reset two indent levels because the dict value is ended implicitly
        stack_top = -1
        if self._tokens.token(idx) in ('}', 'for') and self._cont_stack[-1].token == ':':
            stack_top = -2
        indent = self._cont_stack[stack_top]
        if self._tokens.token(idx) in _CLOSING_BRACKETS:
            valid_offsets = indent.valid_outdent_offsets
        else:
            valid_offsets = indent.valid_continuation_offsets
        return indent, valid_offsets.copy()

    def _hanging_indent_after_bracket(self, bracket, position):
        """Extracts indentation information for a hanging indent."""
        indentation = _get_indent_length(self._tokens.line(position))
        if self._is_block_opener and self._continuation_size == self._block_indent_size:
            return _ContinuedIndent(
                HANGING_BLOCK,
                bracket,
                position,
                _Offsets(indentation + self._continuation_size, indentation),
                _BeforeBlockOffsets(indentation + self._continuation_size,
                                    indentation + self._continuation_size * 2))
        elif bracket == ':':
            if self._cont_stack[-1].context_type == CONTINUED:
                # If the dict key was on the same line as the open brace, the new
                # correct indent should be relative to the key instead of the
                # current indent level
                paren_align = self._cont_stack[-1].valid_outdent_offsets
                next_align = self._cont_stack[-1].valid_continuation_offsets.copy()
                next_align[next_align.keys()[0] + self._continuation_size] = True
            else:
                next_align = _Offsets(indentation + self._continuation_size, indentation)
                paren_align = _Offsets(indentation + self._continuation_size, indentation)
            return _ContinuedIndent(HANGING_DICT_VALUE, bracket, position, paren_align, next_align)
        else:
            return _ContinuedIndent(
                HANGING,
                bracket,
                position,
                _Offsets(indentation, indentation + self._continuation_size),
                _Offsets(indentation + self._continuation_size))

    def _continuation_inside_bracket(self, bracket, pos):
        """Extracts indentation information for a continued indent."""
        indentation = _get_indent_length(self._tokens.line(pos))
        if self._is_block_opener and self._tokens.start_col(pos+1) - indentation == self._block_indent_size:
            return _ContinuedIndent(
                CONTINUED_BLOCK,
                bracket,
                pos,
                _Offsets(self._tokens.start_col(pos)),
                _BeforeBlockOffsets(self._tokens.start_col(pos+1),
                                    self._tokens.start_col(pos+1) + self._continuation_size))
        else:
            return _ContinuedIndent(
                CONTINUED,
                bracket,
                pos,
                _Offsets(self._tokens.start_col(pos)),
                _Offsets(self._tokens.start_col(pos+1)))

    def pop_token(self):
        self._cont_stack.pop()

    def push_token(self, token, position):
        """Pushes a new token for continued indentation on the stack.

        Tokens that can modify continued indentation offsets are:
          * opening brackets
          * 'lambda'
          * : inside dictionaries

        push_token relies on the caller to filter out those
        interesting tokens.

        :param token: The concrete token
        :param position: The position of the token in the stream.
        """
        if _token_followed_by_eol(self._tokens, position):
            self._cont_stack.append(
                self._hanging_indent_after_bracket(token, position))
        else:
            self._cont_stack.append(
                self._continuation_inside_bracket(token, position))


class FormatChecker(BaseTokenChecker):
    """checks for :
    * unauthorized constructions
    * strict indentation
    * line length
    * use of <> instead of !=
    """

    __implements__ = (ITokenChecker, IAstroidChecker, IRawChecker)

    # configuration section name
    name = 'format'
    # messages
    msgs = MSGS
    # configuration options
    # for available dict keys/values see the optik parser 'add_option' method
    options = (('max-line-length',
                {'default' : 80, 'type' : "int", 'metavar' : '<int>',
                 'help' : 'Maximum number of characters on a single line.'}),
               ('ignore-long-lines',
                {'type': 'regexp', 'metavar': '<regexp>',
                 'default': r'^\s*(# )?<?https?://\S+>?$',
                 'help': ('Regexp for a line that is allowed to be longer than '
                          'the limit.')}),
               ('single-line-if-stmt',
                 {'default': False, 'type' : 'yn', 'metavar' : '<y_or_n>',
                  'help' : ('Allow the body of an if to be on the same '
                            'line as the test if there is no else.')}),
               ('no-space-check',
                {'default': ','.join(_NO_SPACE_CHECK_CHOICES),
                 'type': 'multiple_choice',
                 'choices': _NO_SPACE_CHECK_CHOICES,
                 'help': ('List of optional constructs for which whitespace '
                          'checking is disabled')}),
               ('max-module-lines',
                {'default' : 1000, 'type' : 'int', 'metavar' : '<int>',
                 'help': 'Maximum number of lines in a module'}
                ),
               ('indent-string',
                {'default' : '    ', 'type' : "string", 'metavar' : '<string>',
                 'help' : 'String used as indentation unit. This is usually \
"    " (4 spaces) or "\\t" (1 tab).'}),
               ('indent-after-paren',
                {'type': 'int', 'metavar': '<int>', 'default': 4,
                 'help': 'Number of spaces of indent required inside a hanging '
                         ' or continued line.'}),
               )

    def __init__(self, linter=None):
        BaseTokenChecker.__init__(self, linter)
        self._lines = None
        self._visited_lines = None
        self._bracket_stack = [None]

    def _pop_token(self):
        self._bracket_stack.pop()
        self._current_line.pop_token()

    def _push_token(self, token, idx):
        self._bracket_stack.append(token)
        self._current_line.push_token(token, idx)

    def new_line(self, tokens, line_end, line_start):
        """a new line has been encountered, process it if necessary"""
        if _last_token_on_line_is(tokens, line_end, ';'):
            self.add_message('unnecessary-semicolon', line=tokens.start_line(line_end))

        line_num = tokens.start_line(line_start)
        line = tokens.line(line_start)
        if tokens.type(line_start) not in _JUNK_TOKENS:
            self._lines[line_num] = line.split('\n')[0]
        self.check_lines(line, line_num)

    def process_module(self, module):
        self._keywords_with_parens = set()
        if 'print_function' in module.future_imports:
            self._keywords_with_parens.add('print')

    def _check_keyword_parentheses(self, tokens, start):
        """Check that there are not unnecessary parens after a keyword.

        Parens are unnecessary if there is exactly one balanced outer pair on a
        line, and it is followed by a colon, and contains no commas (i.e. is not a
        tuple).

        Args:
        tokens: list of Tokens; the entire list of Tokens.
        start: int; the position of the keyword in the token list.
        """
        # If the next token is not a paren, we're fine.
        if self._inside_brackets(':') and tokens[start][1] == 'for':
            self._pop_token()
        if tokens[start+1][1] != '(':
            return

        found_and_or = False
        depth = 0
        keyword_token = tokens[start][1]
        line_num = tokens[start][2][0]

        for i in xrange(start, len(tokens) - 1):
            token = tokens[i]

            # If we hit a newline, then assume any parens were for continuation.
            if token[0] == tokenize.NL:
                return

            if token[1] == '(':
                depth += 1
            elif token[1] == ')':
                depth -= 1
                if not depth:
                    # ')' can't happen after if (foo), since it would be a syntax error.
                    if (tokens[i+1][1] in (':', ')', ']', '}', 'in') or
                        tokens[i+1][0] in (tokenize.NEWLINE, tokenize.ENDMARKER,
                                             tokenize.COMMENT)):
                        # The empty tuple () is always accepted.
                        if i == start + 2:
                            return
                        if keyword_token == 'not':
                            if not found_and_or:
                                self.add_message('superfluous-parens', line=line_num,
                                                 args=keyword_token)
                        elif keyword_token in ('return', 'yield'):
                            self.add_message('superfluous-parens', line=line_num,
                                             args=keyword_token)
                        elif keyword_token not in self._keywords_with_parens:
                            if not (tokens[i+1][1] == 'in' and found_and_or):
                                self.add_message('superfluous-parens', line=line_num,
                                                 args=keyword_token)
                    return
            elif depth == 1:
                # This is a tuple, which is always acceptable.
                if token[1] == ',':
                    return
                # 'and' and 'or' are the only boolean operators with lower precedence
                # than 'not', so parens are only required when they are found.
                elif token[1] in ('and', 'or'):
                    found_and_or = True
                # A yield inside an expression must always be in parentheses,
                # quit early without error.
                elif token[1] == 'yield':
                    return
                # A generator expression always has a 'for' token in it, and
                # the 'for' token is only legal inside parens when it is in a
                # generator expression.  The parens are necessary here, so bail
                # without an error.
                elif token[1] == 'for':
                    return

    def _opening_bracket(self, tokens, i):
        self._push_token(tokens[i][1], i)
        # Special case: ignore slices
        if tokens[i][1] == '[' and tokens[i+1][1] == ':':
            return

        if (i > 0 and (tokens[i-1][0] == tokenize.NAME and
                       not (keyword.iskeyword(tokens[i-1][1]))
                       or tokens[i-1][1] in _CLOSING_BRACKETS)):
            self._check_space(tokens, i, (_MUST_NOT, _MUST_NOT))
        else:
            self._check_space(tokens, i, (_IGNORE, _MUST_NOT))

    def _closing_bracket(self, tokens, i):
        if self._inside_brackets(':'):
            self._pop_token()
        self._pop_token()
        # Special case: ignore slices
        if tokens[i-1][1] == ':' and tokens[i][1] == ']':
            return
        policy_before = _MUST_NOT
        if tokens[i][1] in _CLOSING_BRACKETS and tokens[i-1][1] == ',':
            if _TRAILING_COMMA in self.config.no_space_check:
                policy_before = _IGNORE

        self._check_space(tokens, i, (policy_before, _IGNORE))

    def _check_equals_spacing(self, tokens, i):
        """Check the spacing of a single equals sign."""
        if self._inside_brackets('(') or self._inside_brackets('lambda'):
            self._check_space(tokens, i, (_MUST_NOT, _MUST_NOT))
        else:
            self._check_space(tokens, i, (_MUST, _MUST))

    def _open_lambda(self, tokens, i): # pylint:disable=unused-argument
        self._push_token('lambda', i)

    def _handle_colon(self, tokens, i):
        # Special case: ignore slices
        if self._inside_brackets('['):
            return
        if (self._inside_brackets('{') and
            _DICT_SEPARATOR in self.config.no_space_check):
            policy = (_IGNORE, _IGNORE)
        else:
            policy = (_MUST_NOT, _MUST)
        self._check_space(tokens, i, policy)

        if self._inside_brackets('lambda'):
            self._pop_token()
        elif self._inside_brackets('{'):
            self._push_token(':', i)

    def _handle_comma(self, tokens, i):
        # Only require a following whitespace if this is
        # not a hanging comma before a closing bracket.
        if tokens[i+1][1] in _CLOSING_BRACKETS:
            self._check_space(tokens, i, (_MUST_NOT, _IGNORE))
        else:
            self._check_space(tokens, i, (_MUST_NOT, _MUST))
        if self._inside_brackets(':'):
            self._pop_token()

    def _check_surrounded_by_space(self, tokens, i):
        """Check that a binary operator is surrounded by exactly one space."""
        self._check_space(tokens, i, (_MUST, _MUST))

    def _check_space(self, tokens, i, policies):
        def _policy_string(policy):
            if policy == _MUST:
                return 'Exactly one', 'required'
            else:
                return 'No', 'allowed'

        def _name_construct(token):
            if tokens[i][1] == ',':
                return 'comma'
            elif tokens[i][1] == ':':
                return ':'
            elif tokens[i][1] in '()[]{}':
                return 'bracket'
            elif tokens[i][1] in ('<', '>', '<=', '>=', '!=', '=='):
                return 'comparison'
            else:
                if self._inside_brackets('('):
                    return 'keyword argument assignment'
                else:
                    return 'assignment'

        good_space = [True, True]
        pairs = [(tokens[i-1], tokens[i]), (tokens[i], tokens[i+1])]

        for other_idx, (policy, token_pair) in enumerate(zip(policies, pairs)):
            if token_pair[other_idx][0] in _EOL or policy == _IGNORE:
                continue

            distance = _column_distance(*token_pair)
            if distance is None:
                continue
            good_space[other_idx] = (
                (policy == _MUST and distance == 1) or
                (policy == _MUST_NOT and distance == 0))

        warnings = []
        if not any(good_space) and policies[0] == policies[1]:
            warnings.append((policies[0], 'around'))
        else:
            for ok, policy, position in zip(good_space, policies, ('before', 'after')):
                if not ok:
                    warnings.append((policy, position))
        for policy, position in warnings:
            construct = _name_construct(tokens[i])
            count, state = _policy_string(policy)
            self.add_message('bad-whitespace', line=tokens[i][2][0],
                             args=(count, state, position, construct,
                                   _underline_token(tokens[i])))

    def _inside_brackets(self, left):
        return self._bracket_stack[-1] == left

    def _handle_old_ne_operator(self, tokens, i):
        if tokens[i][1] == '<>':
            self.add_message('old-ne-operator', line=tokens[i][2][0])

    def _prepare_token_dispatcher(self):
        raw = [
            (_KEYWORD_TOKENS,
             self._check_keyword_parentheses),

            (_OPENING_BRACKETS, self._opening_bracket),

            (_CLOSING_BRACKETS, self._closing_bracket),

            (['='], self._check_equals_spacing),

            (_SPACED_OPERATORS, self._check_surrounded_by_space),

            ([','], self._handle_comma),

            ([':'], self._handle_colon),

            (['lambda'], self._open_lambda),

            (['<>'], self._handle_old_ne_operator),
            ]

        dispatch = {}
        for tokens, handler in raw:
            for token in tokens:
                dispatch[token] = handler
        return dispatch

    def process_tokens(self, tokens):
        """process tokens and search for :

         _ non strict indentation (i.e. not always using the <indent> parameter as
           indent unit)
         _ too long lines (i.e. longer than <max_chars>)
         _ optionally bad construct (if given, bad_construct must be a compiled
           regular expression).
        """
        self._bracket_stack = [None]
        indents = [0]
        check_equal = False
        line_num = 0
        self._lines = {}
        self._visited_lines = {}
        token_handlers = self._prepare_token_dispatcher()

        self._current_line = ContinuedLineState(tokens, self.config)
        for idx, (tok_type, token, start, _, line) in enumerate(tokens):
            if start[0] != line_num:
                line_num = start[0]
                # A tokenizer oddity: if an indented line contains a multi-line
                # docstring, the line member of the INDENT token does not contain
                # the full line; therefore we check the next token on the line.
                if tok_type == tokenize.INDENT:
                    self.new_line(TokenWrapper(tokens), idx-1, idx+1)
                else:
                    self.new_line(TokenWrapper(tokens), idx-1, idx)
            
            if tok_type == tokenize.NEWLINE:
                # a program statement, or ENDMARKER, will eventually follow,
                # after some (possibly empty) run of tokens of the form
                #     (NL | COMMENT)* (INDENT | DEDENT+)?
                # If an INDENT appears, setting check_equal is wrong, and will
                # be undone when we see the INDENT.
                check_equal = True
                self._process_retained_warnings(TokenWrapper(tokens), idx)
                self._current_line.next_logical_line()
            elif tok_type == tokenize.INDENT:
                check_equal = False
                self.check_indent_level(token, indents[-1]+1, line_num)
                indents.append(indents[-1]+1)
            elif tok_type == tokenize.DEDENT:
                # there's nothing we need to check here!  what's important is
                # that when the run of DEDENTs ends, the indentation of the
                # program statement (or ENDMARKER) that triggered the run is
                # equal to what's left at the top of the indents stack
                check_equal = True
                if len(indents) > 1:
                    del indents[-1]
            elif tok_type == tokenize.NL:
                self._check_continued_indentation(TokenWrapper(tokens), idx+1)
                self._current_line.next_physical_line()
            elif tok_type != tokenize.COMMENT:
                self._current_line.handle_line_start(idx)
                # This is the first concrete token following a NEWLINE, so it
                # must be the first token of the next program statement, or an
                # ENDMARKER; the "line" argument exposes the leading whitespace
                # for this statement; in the case of ENDMARKER, line is an empty
                # string, so will properly match the empty string with which the
                # "indents" stack was seeded
                if check_equal:
                    check_equal = False
                    self.check_indent_level(line, indents[-1], line_num)

            if tok_type == tokenize.NUMBER and token.endswith('l'):
                self.add_message('lowercase-l-suffix', line=line_num)

            try:
                handler = token_handlers[token]
            except KeyError:
                pass
            else:
                handler(tokens, idx)

        line_num -= 1 # to be ok with "wc -l"
        if line_num > self.config.max_module_lines:
            self.add_message('too-many-lines', args=line_num, line=1)

    def _process_retained_warnings(self, tokens, current_pos):
        single_line_block_stmt = not _last_token_on_line_is(tokens, current_pos, ':')

        for indent_pos, state, offsets in self._current_line.retained_warnings:
            block_type = offsets[tokens.start_col(indent_pos)]
            hints = dict((k, v) for k, v in offsets.iteritems()
                         if v != block_type)
            if single_line_block_stmt and block_type == WITH_BODY:
                self._add_continuation_message(state, hints, tokens, indent_pos)
            elif not single_line_block_stmt and block_type == SINGLE_LINE:
                self._add_continuation_message(state, hints, tokens, indent_pos)

    def _check_continued_indentation(self, tokens, next_idx):
        # Do not issue any warnings if the next line is empty.
        if not self._current_line.has_content or tokens.type(next_idx) == tokenize.NL:
            return

        state, valid_offsets = self._current_line.get_valid_offsets(next_idx)
        # Special handling for hanging comments. If the last line ended with a
        # comment and the new line contains only a comment, the line may also be
        # indented to the start of the previous comment.
        if (tokens.type(next_idx) == tokenize.COMMENT and
                tokens.type(next_idx-2) == tokenize.COMMENT):
            valid_offsets[tokens.start_col(next_idx-2)] = True

        # We can only decide if the indentation of a continued line before opening
        # a new block is valid once we know of the body of the block is on the
        # same line as the block opener. Since the token processing is single-pass,
        # emitting those warnings is delayed until the block opener is processed.
        if (state.context_type in (HANGING_BLOCK, CONTINUED_BLOCK)
                and tokens.start_col(next_idx) in valid_offsets):
            self._current_line.add_block_warning(next_idx, state, valid_offsets)
        elif tokens.start_col(next_idx) not in valid_offsets:
            self._add_continuation_message(state, valid_offsets, tokens, next_idx)

    def _add_continuation_message(self, state, offsets, tokens, position):
        readable_type, readable_position = _CONTINUATION_MSG_PARTS[state.context_type]
        hint_line = _get_indent_hint_line(offsets, tokens.start_col(position))
        self.add_message(
            'bad-continuation',
            line=tokens.start_line(position),
            args=(readable_type, readable_position, tokens.line(position), hint_line))

    @check_messages('multiple-statements')
    def visit_default(self, node):
        """check the node line number and check it if not yet done"""
        if not node.is_statement:
            return
        if not node.root().pure_python:
            return # XXX block visit of child nodes
        prev_sibl = node.previous_sibling()
        if prev_sibl is not None:
            prev_line = prev_sibl.fromlineno
        else:
            # The line on which a finally: occurs in a try/finally
            # is not directly represented in the AST. We infer it
            # by taking the last line of the body and adding 1, which
            # should be the line of finally:
            if (isinstance(node.parent, nodes.TryFinally)
                and node in node.parent.finalbody):
                prev_line = node.parent.body[0].tolineno + 1
            else:
                prev_line = node.parent.statement().fromlineno
        line = node.fromlineno
        assert line, node
        if prev_line == line and self._visited_lines.get(line) != 2:
            self._check_multi_statement_line(node, line)
            return
        if line in self._visited_lines:
            return
        try:
            tolineno = node.blockstart_tolineno
        except AttributeError:
            tolineno = node.tolineno
        assert tolineno, node
        lines = []
        for line in xrange(line, tolineno + 1):
            self._visited_lines[line] = 1
            try:
                lines.append(self._lines[line].rstrip())
            except KeyError:
                lines.append('')

    def _check_multi_statement_line(self, node, line):
        """Check for lines containing multiple statements."""
        # Do not warn about multiple nested context managers
        # in with statements.
        if isinstance(node, nodes.With):
            return
        # For try... except... finally..., the two nodes
        # appear to be on the same line due to how the AST is built.
        if (isinstance(node, nodes.TryExcept) and
            isinstance(node.parent, nodes.TryFinally)):
            return
        if (isinstance(node.parent, nodes.If) and not node.parent.orelse
            and self.config.single_line_if_stmt):
            return
        self.add_message('multiple-statements', node=node)
        self._visited_lines[line] = 2

    @check_messages('backtick')
    def visit_backquote(self, node):
        self.add_message('backtick', node=node)

    def check_lines(self, lines, i):
        """check lines have less than a maximum number of characters
        """
        max_chars = self.config.max_line_length
        ignore_long_line = self.config.ignore_long_lines

        for line in lines.splitlines(True):
            if not line.endswith('\n'):
                self.add_message('missing-final-newline', line=i)
            else:
                stripped_line = line.rstrip()
                if line[len(stripped_line):] not in ('\n', '\r\n'):
                    self.add_message('trailing-whitespace', line=i)
                # Don't count excess whitespace in the line length.
                line = stripped_line
            mobj = OPTION_RGX.search(line)
            if mobj and mobj.group(1).split('=', 1)[0].strip() == 'disable':
                line = line.split('#')[0].rstrip()

            if len(line) > max_chars and not ignore_long_line.search(line):
                self.add_message('line-too-long', line=i, args=(len(line), max_chars))
            i += 1

    def check_indent_level(self, string, expected, line_num):
        """return the indent level of the string
        """
        indent = self.config.indent_string
        if indent == '\\t': # \t is not interpreted in the configuration file
            indent = '\t'
        level = 0
        unit_size = len(indent)
        while string[:unit_size] == indent:
            string = string[unit_size:]
            level += 1
        suppl = ''
        while string and string[0] in ' \t':
            if string[0] != indent[0]:
                if string[0] == '\t':
                    args = ('tab', 'space')
                else:
                    args = ('space', 'tab')
                self.add_message('mixed-indentation', args=args, line=line_num)
                return level
            suppl += string[0]
            string = string[1:]
        if level != expected or suppl:
            i_type = 'spaces'
            if indent[0] == '\t':
                i_type = 'tabs'
            self.add_message('bad-indentation', line=line_num,
                             args=(level * unit_size + len(suppl), i_type,
                                   expected * unit_size))


def register(linter):
    """required method to auto register this checker """
    linter.register_checker(FormatChecker(linter))
