import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isDirectChat,
  isDirectCliDirective,
  parseDirectProjectDirective,
} from '../src/direct-intake.mjs'

test('accepts only an explicit Proyecto directive', () => {
  assert.deepEqual(parseDirectProjectDirective('Proyecto: proyecto-inmobiliaria'), {
    projectHint: 'proyecto-inmobiliaria',
  })
  assert.deepEqual(parseDirectProjectDirective('  PROYECTO :  Proyecto Inmobiliaria  '), {
    projectHint: 'Proyecto Inmobiliaria',
  })
  assert.equal(parseDirectProjectDirective('proyecto inmobiliaria'), null)
  assert.equal(parseDirectProjectDirective('Esto es para proyecto: rentid'), null)
})

test('recognizes private WhatsApp chat identifiers', () => {
  assert.equal(isDirectChat('5491111111111@s.whatsapp.net'), true)
  assert.equal(isDirectChat('12345@lid'), true)
  assert.equal(isDirectChat('12345@g.us'), false)
})

test('accepts CLI only as a standalone direct bridge directive', () => {
  assert.equal(isDirectCliDirective('CLI'), true)
  assert.equal(isDirectCliDirective(' cli '), true)
  assert.equal(isDirectCliDirective('CLI: codex-cli-mobile-bridge'), false)
  assert.equal(isDirectCliDirective('Usar CLI'), false)
})
