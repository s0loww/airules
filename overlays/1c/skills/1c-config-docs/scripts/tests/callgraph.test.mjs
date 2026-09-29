// callgraph.mjs: enum values referenced only by ConfigDumpInfo.xml are unreferenced.
// ConfigDumpInfo.xml is the dump's table of contents: it lists every value of every enum, and
// counting it as a reference once made the "unreferenced values" list empty on every dump.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const SCRIPTS = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');

const ENUM_XML = `﻿<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core" version="2.17">
\t<Enum uuid="11111111-1111-1111-1111-111111111111">
\t\t<Properties>
\t\t\t<Name>Цвета</Name>
\t\t</Properties>
\t\t<ChildObjects>
\t\t\t<EnumValue uuid="22222222-2222-2222-2222-222222222222">
\t\t\t\t<Properties>
\t\t\t\t\t<Name>Красный</Name>
\t\t\t\t</Properties>
\t\t\t</EnumValue>
\t\t\t<EnumValue uuid="33333333-3333-3333-3333-333333333333">
\t\t\t\t<Properties>
\t\t\t\t\t<Name>Синий</Name>
\t\t\t\t</Properties>
\t\t\t</EnumValue>
\t\t</ChildObjects>
\t</Enum>
</MetaDataObject>
`;

const DUMP_INFO = `﻿<?xml version="1.0" encoding="UTF-8"?>
<ConfigDumpInfo xmlns="http://v8.1c.ru/8.3/xcf/dumpinfo" format="Hierarchical" version="2.17">
\t<ConfigVersions>
\t\t<Metadata name="Enum.Цвета" id="11111111-1111-1111-1111-111111111111" configVersion="0">
\t\t\t<Metadata name="Enum.Цвета.EnumValue.Красный" id="22222222-2222-2222-2222-222222222222"/>
\t\t\t<Metadata name="Enum.Цвета.EnumValue.Синий" id="33333333-3333-3333-3333-333333333333"/>
\t\t</Metadata>
\t</ConfigVersions>
</ConfigDumpInfo>
`;

const MODULE_BSL = `﻿Процедура Покрасить() Экспорт
\tЦвет = Перечисления.Цвета.Красный;
КонецПроцедуры
`;

function write(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text, 'utf8');
}

test('an enum value listed only in ConfigDumpInfo.xml is reported as unreferenced', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'callgraph-test-'));
  try {
    const src = path.join(root, 'src');
    write(path.join(src, 'Enums', 'Цвета.xml'), ENUM_XML);
    write(path.join(src, 'ConfigDumpInfo.xml'), DUMP_INFO);
    write(path.join(src, 'CommonModules', 'Краски', 'Ext', 'Module.bsl'), MODULE_BSL);
    const cfg = path.join(root, 'cfg.json');
    write(cfg, JSON.stringify({
      languages: { primary: { code: 'ru' } },
      outputRoot: path.join(root, 'out'),
      source: { worktree: root, srcRoot: 'src', commit: 'test' },
      sets: [{ id: 'b', dir: '.', diagramPrefix: 'x-', title: 'T' }],
    }));

    execFileSync(process.execPath, [path.join(SCRIPTS, 'callgraph.mjs'), '--config', cfg], { stdio: 'pipe' });
    const out = JSON.parse(fs.readFileSync(path.join(root, 'out', '_facts', 'callgraph.json'), 'utf8'));

    assert.ok(out.unreferencedEnumValues.includes('Цвета.Синий'), `Синий must be unreferenced: ${JSON.stringify(out.unreferencedEnumValues)}`);
    assert.ok(!out.unreferencedEnumValues.includes('Цвета.Красный'), 'Красный is referenced from the module');
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
