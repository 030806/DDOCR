import {it,expect} from 'vitest'
import {regionDisplayPage,originalPolygon,containsBox} from './regionImageView'
import type {OcrPage,RegionImage,OcrPolygon} from './types/ocr'
it('maps region display and edited geometry without mutating the original page',()=>{
 const polygon:OcrPolygon=[[110,220],[150,220],[150,250],[110,250]]
 const page:OcrPage={no:1,label:'original',sourceWidth:1000,sourceHeight:1000,items:[{id:'a',text:'A',bbox:[110,220,150,250],polygon,score:1,comments:[]},{id:'b',text:'B',bbox:[0,0,20,20],score:1,comments:[]}],terminalPoints:[{id:'p',x:130,y:240,source:'model',terminal_number:'XT-Z'},{id:'q',x:10,y:10,source:'model'}]}
 const region:RegionImage={id:'r',label:'region',bbox:[100,200,200,300],width:100,height:100,imageUrl:'crop'}
 const view=regionDisplayPage(page,region)
 expect(view.items[0]!.bbox).toEqual([10,20,50,50]);expect(view.items).toHaveLength(1)
 expect(view.terminalPoints![0]).toMatchObject({id:'p',x:30,y:40,terminal_number:'XT-Z'})
 expect(originalPolygon(view.items[0]!.polygon!,region)).toEqual(polygon)
 expect(page.items[0]!.bbox).toEqual([110,220,150,250]);expect(page.terminalPoints).toHaveLength(2)
 expect(containsBox(region,page.items[0]!.bbox)).toBe(true)
 expect(containsBox(region,[50,200,150,250])).toBe(false)
})
