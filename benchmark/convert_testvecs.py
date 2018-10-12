#!/usr/bin/env python3
# Copyright 2018 Google LLC
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Import test vectors from hpolyc/test_vectors/ours/."""

import argparse
import pathlib
import random
import sys

scriptdir = pathlib.Path(__file__).parent
targetdir = scriptdir / "testvectors"
hpcdir = scriptdir.resolve().parent

sys.path.append(str(hpcdir / "python"))

import hexjson

def group_string(s, l):
    for i in range(0, len(s), l):
        yield s[i:i+l]

def c_stringify(b):
    return '"' + ''.join(f"\\x{a:02x}" for a in b) + '"'

def write_in_groups(f, prefix, separator, suffix, emptyval, values):
    first = True
    for v in values:
        if first:
            f.write(prefix)
            first = False
        else:
            f.write(separator)
        f.write(v)
    if first:
        f.write(emptyval)
    else:
        f.write(suffix)

def write_testvec_structs(f, declaration, entries):
    f.write(f"{declaration} = {{\n")
    for vec in entries:
        f.write("\t{\n")
        for k, v in vec.items():
            f.write(f"\t\t.{k}\t= {{.len = {len(v)}, .data =")
            write_in_groups(f, '\n\t\t\t', '\n\t\t\t', '\n\t\t', ' ""',
                (c_stringify(s) for s in group_string(v, 8)))
            f.write('},\n')
        f.write("\t},\n")
    f.write(f"}};\n\n")

def choose(n, k):
    "k distinct integers 0 <= x < n, sorted"
    t = n - k + 1
    d = []
    for _ in range(k):
        r = random.randrange(t + len(d))
        if r < t:
            d.append(r)
        else:
            d.append(d[r - t])
    d.sort()
    return [i + v for i, v in enumerate(d)]

def partition_int(length, maxparts):
    """Randomly generate 1 to maxparts integers >0 that sum to length"""
    if length <= 0:
        return [length]
    numsplits = random.randrange(min(length, maxparts))
    splits = choose(length - 1, numsplits)
    return [b - a for a, b in zip([-1] + splits, splits + [length -1])]

def write_linux_testvec_hexfield(f, field_name, value):
    """Write a hex field to a Linux crypto test vector."""
    f.write(f'\t\t.{field_name}\t=')
    write_in_groups(f, ' ', '\n\t\t\t  ', '', ' ""',
        (c_stringify(s) for s in group_string(value, 8)))
    f.write(',\n')

def write_linux_cipher_testvecs(f, cipher_name, entries):
    """Format some cipher test vectors for Linux's crypto tests."""
    f.write(f"static const struct cipher_testvec {cipher_name}_template[] = {{\n")
    first = True
    for vec in entries:
        if first:
            f.write("\t{\n")
            first = False
        else:
            f.write(", {\n")
        write_linux_testvec_hexfield(f, "key", vec['input']['key'])
        f.write(f"\t\t.klen\t= {len(vec['input']['key'])},\n")
        write_linux_testvec_hexfield(f, "iv", vec['input']['tweak'])
        write_linux_testvec_hexfield(f, "ptext", vec['plaintext'])
        write_linux_testvec_hexfield(f, "ctext", vec['ciphertext'])
        length = len(vec['plaintext'])
        f.write(f"\t\t.len\t= {length},\n")
        splits = partition_int(length, 8)
        if len(splits) > 1:
            f.write("\t\t.also_non_np = 1,\n")
            f.write(f"\t\t.np\t= {len(splits)},\n")
            f.write(f"\t\t.tap\t= {{ {', '.join(str(split) for split in splits)} }},\n")
        f.write("\t}")
    f.write('\n};\n\n')

def sample_adiantum_testvecs(all_vecs):
    """Select some Adiantum test vectors to include in Linux's crypto tests."""
    have_lens = set()
    for vec in all_vecs:

        # Linux's crypto API supports only one tweak length per cipher.  We've
        # chosen 32 bytes, so exclude tests for other tweak lengths.
        if len(vec['input']['tweak']) != 32:
            continue

        # There isn't room for a huge number of test vectors, so just use one of
        # the "random" tests for each length that was generated.
        if 'Random' not in vec['description']:
            continue
        length = len(vec['plaintext'])
        if length in have_lens:
          continue

        have_lens.add(length)
        yield vec

def convert_hbsh_testvec(v):
    return {
        'key': v['input']['key'],
        'tweak': v['input']['tweak'],
        'plaintext': v['plaintext'],
        'ciphertext': v['ciphertext'],
    }

def hpc_vectors(variant, nrounds):
    yield from hexjson.iter_unhex(hpcdir / "test_vectors" / "ours" / variant /
        f'{variant}_XChaCha{nrounds}_32_AES256.json')

def hbsh(variant):
    """Convert test vectors for the given HBSH variant."""

    target = targetdir / f"{variant.lower()}_testvecs.h"
    with target.open("w") as f:
        f.write("/* GENERATED BY convert_testvecs.py, DO NOT EDIT */\n\n")
        for nrounds in [20, 12, 8]:
            write_testvec_structs(f,
                f'static const struct hbsh_testvec {variant.lower()}_xchacha{nrounds}_aes256_tv[]',
                (convert_hbsh_testvec(s) for s in hpc_vectors(variant, nrounds)))

def hbsh_linux(variant):
    # Optionally format Adiantum's test vectors for the Linux kernel's crypto tests.
    target = targetdir / f"{variant.lower()}_testvecs_linux.h"
    with target.open("w") as f:
        for nrounds in [12, 20]:
            write_linux_cipher_testvecs(f,
                f'hbsh_xchacha{nrounds}_aes_nhpoly1305_tv',
                sample_adiantum_testvecs(hpc_vectors(variant, nrounds)))


def convert_nh_testvec(v):
    return {
        'key': v['input']['key'],
        'message': v['input']['message'],
        'hash': v['hash'],
    }

def nh():
    """Convert the NH test vectors."""
    vectors = hpcdir / "test_vectors" / "ours" / "NH"
    target = targetdir / "nh_testvecs.h"
    with target.open("w") as f:
        f.write("/* GENERATED BY convert_testvecs.py, DO NOT EDIT */\n\n")
        vectorfile = vectors / f'NH.json'
        write_testvec_structs(f,
            'static const struct nh_testvec nh_tv[]',
            (convert_nh_testvec(s) for s in hexjson.iter_unhex(vectorfile)))

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--linux', action='store_true')
    return p.parse_args()

def main():
    random.seed(0)
    args = parse_args()
    hbsh('HPolyC')
    hbsh('Adiantum')
    nh()
    if args.linux:
        hbsh_linux('Adiantum')

if __name__ == "__main__":
    main()
