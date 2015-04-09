# -*- coding: utf-8 -*-
# <Lettuce - Behaviour Driven Development for python>
# Copyright (C) <2010-2012>  Gabriel Falcão <gabriel@nacaolivre.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from lychee.registry import STEP_REGISTRY


def _is_step_sentence(sentence):
    return isinstance(sentence, str) or isinstance(sentence, basestring)


def step(step_func_or_sentence):
    """Decorates a function, so that it will become a new step
    definition.
    You give step sentence either (by priority):
    * with step function argument (first example)
    * with function doc (second example)
    * with the function name exploded by underscores (third example)
    """
    if _is_step_sentence(step_func_or_sentence):
        return lambda func: STEP_REGISTRY.load(step_func_or_sentence, func)
    else:
        return STEP_REGISTRY.load_func(step_func_or_sentence)
