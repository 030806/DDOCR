export type TerminalNumbering = {start:number;number_prefix?:string;numbering_mode?:'numeric'|'alpha';letter_start?:string;letter_case?:'upper'|'lower'}
export function terminalLabel(rule:TerminalNumbering, offset:number):string {
  const prefix=rule.number_prefix ?? ''
  if(typeof prefix!=='string' || prefix.length>40 || /[\x00-\x1f\x7f]/.test(prefix)) return ''
  if(!Number.isSafeInteger(offset) || offset<0) return ''
  if((rule.numbering_mode || 'numeric')==='numeric') return Number.isSafeInteger(rule.start) && rule.start>=0 && Number.isSafeInteger(rule.start+offset)?prefix+String(rule.start+offset):''
  const start=rule.letter_start ?? 'A'
  if(!/^[A-Za-z]{1,10}$/.test(start)) return ''
  let value=0
  for(const char of start.toUpperCase()) value=value*26+char.charCodeAt(0)-64
  value+=offset
  let text=''
  while(value>0){value--;text=String.fromCharCode(65+value%26)+text;value=Math.floor(value/26)}
  return prefix+(rule.letter_case==='lower'?text.toLowerCase():text)
}
