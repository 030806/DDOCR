import {describe,it,expect} from 'vitest'
import {terminalLabel} from './terminalNumbering'
describe('terminal hole numbering',()=>{
  it('retains legacy numeric numbering including zero',()=>{
    expect(terminalLabel({start:0},2)).toBe('2')
    expect(terminalLabel({start:7},3)).toBe('10')
  })
  it('continues alphabetic labels across Z and ZZ',()=>{
    const rule={start:1,numbering_mode:'alpha' as const,letter_start:'Z'}
    expect([0,1,2].map(i=>terminalLabel(rule,i))).toEqual(['Z','AA','AB'])
    expect(terminalLabel({...rule,letter_start:'ZZ'},1)).toBe('AAA')
    expect(terminalLabel({...rule,letter_start:'az',letter_case:'lower'},1)).toBe('ba')
  })
  it.each(['','A1','中','Α','A B','AAAAAAAAAAA'])('rejects invalid alphabet starts %s',letter_start=>{
    expect(terminalLabel({start:1,numbering_mode:'alpha',letter_start},0)).toBe('')
  })
  it('adds a hole-number prefix without using the wire naming prefix',()=>{
    expect(terminalLabel({start:1,number_prefix:'XT-'},1)).toBe('XT-2')
    expect(terminalLabel({start:1,numbering_mode:'alpha',letter_start:'Z',number_prefix:'XT-'},1)).toBe('XT-AA')
    expect(terminalLabel({start:1,numbering_mode:'alpha',letter_start:'A',letter_case:'lower',number_prefix:'XT-'},0)).toBe('XT-a')
    expect(terminalLabel({start:1,number_prefix:'x'.repeat(41)},0)).toBe('')
  })

})
