#!/usr/bin/env python3

import sys
import subprocess
import json
from argparse import ArgumentParser
from dataclasses import dataclass
from enum import Enum
from glob import glob
from pathlib import Path
from typing import List, Optional, Tuple, Union


class SMTUse(Enum):
    PRESERVE = 'preserve'
    DISABLE = 'disable'
    STRIP_PRAGMAS = 'strip-pragmas'


@dataclass(frozen=True)
class ContractReport:
    contract_name: str
    file_name: Path
    bytecode: Optional[str]
    metadata: Optional[str]


@dataclass
class FileReport:
    file_name: Path
    contract_reports: Optional[List[ContractReport]]

    def format_report(self) -> str:
        report = ""

        if self.contract_reports is None:
            return f"{self.file_name}: <ERROR>\n"

        for contract_report in self.contract_reports:
            bytecode = contract_report.bytecode if contract_report.bytecode is not None else '<NO BYTECODE>'
            metadata = contract_report.metadata if contract_report.metadata is not None else '<NO METADATA>'

            # NOTE: Ignoring contract_report.file_name because it should always be either the same
            # as self.file_name (for Standard JSON) or just the '<stdin>' placeholder (for CLI).
            report += f"{self.file_name}:{contract_report.contract_name} {bytecode}\n"
            report += f"{self.file_name}:{contract_report.contract_name} {metadata}\n"

        return report


def load_source(path: Union[Path, str], smt_use: SMTUse) -> str:
    with open(path, mode='r', encoding='utf8') as source_file:
        file_content = source_file.read()

    if smt_use == SMTUse.STRIP_PRAGMAS:
        return file_content.replace('pragma experimental SMTChecker;', '')

    return file_content


def parse_standard_json_output(source_file_name: Path, standard_json_output: str) -> FileReport:
    decoded_json_output = json.loads(standard_json_output.strip())

    if 'contracts' not in decoded_json_output:
        return FileReport(file_name=source_file_name, contract_reports=None)

    file_report = FileReport(file_name=source_file_name, contract_reports=[])
    for file_name, file_results in sorted(decoded_json_output['contracts'].items()):
        for contract_name, contract_results in sorted(file_results.items()):
            assert file_report.contract_reports is not None
            file_report.contract_reports.append(ContractReport(
                contract_name=contract_name,
                file_name=Path(file_name),
                bytecode=contract_results.get('evm', {}).get('bytecode', {}).get('object'),
                metadata=contract_results.get('metadata'),
            ))

    return file_report


def prepare_compiler_input(compiler_path: Path, source_file_name: Path, optimize: bool, smt_use: SMTUse) -> Tuple[List[str], str]:
    json_input: dict = {
        'language': 'Solidity',
        'sources': {
            str(source_file_name): {'content': load_source(source_file_name, smt_use)}
        },
        'settings': {
            'optimizer': {'enabled': optimize},
            'outputSelection': {'*': {'*': ['evm.bytecode.object', 'metadata']}},
        }
    }

    if smt_use == SMTUse.DISABLE:
        json_input['settings']['modelChecker'] = {'engine': 'none'}

    command_line = [str(compiler_path), '--standard-json']
    compiler_input = json.dumps(json_input)

    return (command_line, compiler_input)


def run_compiler(compiler_path: Path, source_file_name: Path, optimize: bool, smt_use: SMTUse) -> FileReport:
    (command_line, compiler_input) = prepare_compiler_input(compiler_path, Path(source_file_name).name, optimize, smt_use)

    process = subprocess.run(
        command_line,
        input=compiler_input,
        encoding='utf8',
        capture_output=True,
    )

    return parse_standard_json_output(Path(source_file_name), process.stdout)


def generate_report(source_file_names: List[str], compiler_path: Path, smt_use: SMTUse):
    with open('report.txt', mode='w', encoding='utf8', newline='\n') as report_file:
        for optimize in [False, True]:
            for source_file_name in sorted(source_file_names):
                try:
                    report = run_compiler(Path(compiler_path), Path(source_file_name), optimize, smt_use)
                    report_file.write(report.format_report())
                except subprocess.CalledProcessError as exception:
                    print(f"\n\nInterrupted by an exception while processing file '{source_file_name}' with optimize={optimize}\n", file=sys.stderr)
                    print(f"COMPILER STDOUT:\n{exception.stdout}", file=sys.stderr)
                    print(f"COMPILER STDERR:\n{exception.stderr}", file=sys.stderr)
                    raise
                except:
                    print(f"\n\nInterrupted by an exception while processing file '{source_file_name}' with optimize={optimize}\n", file=sys.stderr)
                    raise


def commandline_parser() -> ArgumentParser:
    script_description = (
        "Generates a report listing bytecode and metadata obtained by compiling all the "
        "*.sol files found in the current working directory using the provided binary."
    )

    parser = ArgumentParser(description=script_description)
    parser.add_argument(dest='compiler_path', help="Solidity compiler executable")
    parser.add_argument('--smt-use', dest='smt_use', default=SMTUse.DISABLE.value, choices=[s.value for s in SMTUse], help="What to do about contracts that use the experimental SMT checker.")
    return parser;


if __name__ == "__main__":
    options = commandline_parser().parse_args()
    generate_report(
        glob("*.sol"),
        Path(options.compiler_path),
        SMTUse(options.smt_use),
    )
