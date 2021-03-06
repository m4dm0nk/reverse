#!/bin/python3
#
# Reverse : reverse engineering for x86 binaries
# Copyright (C) 2015    Joel
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.    If not, see <http://www.gnu.org/licenses/>.
#


import lib.ast
from lib.colors import *
from lib.utils import *
from capstone.x86 import *


binary = None
nocomment = False


def print_block(blk, tab):
    for i in blk:
        print_inst(i, tab)


def print_tabbed(string, tab):
    print("    " * tab, end="")
    print(string)


def print_tabbed_no_end(string, tab):
    print("    " * tab, end="")
    print(string, end="")


def print_no_end(text):
    print(text, end="")


def print_symbol(addr):
    print_no_end(color_string("<" + binary.reverse_symbols[addr] + ">"))


# Return True if the operand is a variable (because the output is
# modified, we reprint the original instruction later)
def print_operand(i, num_op, hexa=False):
    def inv(n):
        return n == X86_OP_INVALID

    op = i.operands[num_op]

    if op.type == X86_OP_IMM:
        imm = op.value.imm

        if binary.is_rodata(imm):
            print_no_end("0x%x " % imm)
            print_no_end(color_string(binary.get_string(imm)))

        elif imm in binary.reverse_symbols:
            print_no_end("0x%x " % imm)
            print_symbol(imm)

        else:
            if hexa:
                print_no_end("0x%x" % imm)
            else:
                if op.size == 1:
                    print_no_end(color_string("'%s'" % get_char(imm)))
                else:
                    print_no_end(str(imm))
        return False

    elif op.type == X86_OP_REG:
        print_no_end(i.reg_name(op.value.reg))
        return False

    elif op.type == X86_OP_FP:
        print_no_end("%f" % op.value.fp)
        return False

    elif op.type == X86_OP_MEM:
        mm = op.mem

        if not inv(mm.base) and mm.disp != 0 \
            and inv(mm.segment) and inv(mm.index):

            if (mm.base == X86_REG_RBP or mm.base == X86_REG_EBP) and \
                   var_name_exists(i, num_op): 
                print_no_end(color_var(get_var_name(i, num_op)))
                return True
            elif mm.base == X86_REG_RIP or mm.base == X86_REG_EIP:
                print_no_end("[" + "0x%x" % (i.address + mm.disp) + "]")
                return True

        printed = False
        print_no_end("[")

        if not inv(mm.base):
            print_no_end("%s" % i.reg_name(mm.base))
            printed = True

        elif not inv(mm.segment):
            print_no_end("%s" % i.reg_name(mm.segment))
            printed = True

        if not inv(mm.index):
            if printed:
                print_no_end(" + ")
            if mm.scale == 1:
                print_no_end("%s" % i.reg_name(mm.index))
            else:
                print_no_end("(%s*%d)" % (i.reg_name(mm.index), mm.scale))
            printed = True

        if mm.disp != 0:
            if mm.disp < 0:
                if printed:
                    print_no_end(" - ")
                print_no_end(-mm.disp)
            else:
                if printed:
                    print_no_end(" + ")
                    print_no_end(mm.disp)
                else:
                    if mm.disp in binary.reverse_symbols:
                        print_no_end("0x%x " % mm.disp)
                        print_symbol(mm.disp)
                    else:
                        print_no_end("0x%x" % mm.disp)

        print_no_end("]")
        return True


def var_name_exists(i, op_num):
    return i.operands[op_num].mem.disp in lib.ast.local_vars_idx


def get_var_name(i, op_num):
    idx = lib.ast.local_vars_idx[i.operands[op_num].mem.disp]
    return lib.ast.local_vars_name[idx]


def get_addr(i):
    addr_str = "0x%x: " % i.address
    if i.address in addr_color:
        addr_str = color(addr_str, addr_color[i.address])
    else:
        addr_str = color_addr(addr_str)
    return addr_str


# Only used when --nocomment is enabled and a jump point to this instruction
def print_addr_if_req(i, tab):
    if i.address in addr_color:
        print_tabbed(get_addr(i), tab)


def print_comment_no_end(txt, tab=-1):
    if tab == -1:
        print_no_end(color_comment(txt))
    else:
        print_tabbed_no_end(color_comment(txt), tab)


def print_cmp_jump_commented(cmp_inst, jump_inst, tab):
    if not nocomment:
        if cmp_inst != None:
            print_inst(cmp_inst, tab, "# ")
        print_inst(jump_inst, tab, "# ")
    else:
        # Otherwise print only the address if referenced
        if cmp_inst != None:
            print_addr_if_req(cmp_inst, tab)
        print_addr_if_req(jump_inst, tab)


def print_cmp_in_if(cmp_inst, jump_id):
    if cmp_inst != None:
        print_no_end("(")
        print_operand(cmp_inst, 0)
        print_no_end(" ")

    print_no_end(cond_sign_str(jump_id, cmp_inst != None))

    if cmp_inst != None:
        print_no_end(" ")
        print_operand(cmp_inst, 1)
        print_no_end(")")


def print_comment(txt, tab=-1):
    if tab == -1:
        print(color_comment(txt))
    else:
        print_tabbed(color_comment(txt), tab)


def print_inst(i, tab=0, prefix=""):
    def get_inst_str():
        nonlocal i
        return "%s %s" % (i.mnemonic, i.op_str)


    if prefix == "# ":
        if not nocomment:
            print_comment_no_end(prefix, tab)
            print_no_end(get_addr(i))
            print_comment(get_inst_str())
        return

    print_tabbed_no_end(get_addr(i), tab)

    if is_ret(i):
        print(color_retcall(get_inst_str()))
        return

    if is_call(i):
        print_no_end(color_retcall(i.mnemonic) + " ")
        print_operand(i, 0, hexa=True)
        print()
        return

    # Here we can have conditional jump with the option --dump
    if is_jump(i):
        if i.operands[0].type != X86_OP_IMM:
            print_no_end(i.mnemonic + " ")
            print_operand(i, 0)
            print()
            return
        try:
            addr = i.operands[0].value.imm
            print(i.mnemonic + " " + color("0x%x" % addr, addr_color[addr]))
        except Exception:
            print(i.mnemonic + " 0x%x" % addr)
        return

    
    modified = False

    inst_check = [X86_INS_SUB, X86_INS_ADD, X86_INS_MOV, X86_INS_CMP]

    if i.id in inst_check:
        print_operand(i, 0)
        print_no_end(" " + cond_sign_str(i.id) + " ")
        print_operand(i, 1)
        modified = True
    else:
        print_no_end("%s " % i.mnemonic)
        if len(i.operands) > 0:
            modified = print_operand(i, 0)
            k = 1
            while k < len(i.operands):
                print_no_end(", ")
                modified |= print_operand(i, k)
                k += 1

    if modified and not nocomment:
        print_comment_no_end(" # " + get_inst_str())

    print()


def print_ast(entry, ast):
    print_no_end(color_keyword("function "))
    print_no_end(binary.reverse_symbols.get(entry, hex(entry)))
    print(" {")
    print_vars_type()
    ast.print(1)
    print("}")


def print_vars_type():
    idx = 0
    for sz in lib.ast.local_vars_size:
        name = lib.ast.local_vars_name[idx]
        print_tabbed(color_type("int%d_t " % (sz*8)) + color_var(name), 1)
        idx += 1
