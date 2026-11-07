import type {OcrPage,OcrPolygon,RegionImage} from './types/ocr'
export function containsBox(region:RegionImage,box:OcrPage['items'][number]['bbox']) {
 const [x,y,right,bottom]=region.bbox
 return box[0]>=x && box[1]>=y && box[2]<=right && box[3]<=bottom
}
export function itemsInRegion(page: OcrPage, region: RegionImage) {
 const [x,y,right,bottom]=region.bbox
 return page.items.filter(i=>(!i.sourceRegionId || !page.regionImages?.some(r=>r.id===i.sourceRegionId) || i.sourceRegionId===region.id) && i.bbox[0]<right && i.bbox[2]>x && i.bbox[1]<bottom && i.bbox[3]>y)
}
export function regionDisplayPage(page:OcrPage,region:RegionImage):OcrPage {
 const [x,y,right,bottom]=region.bbox
 return {...page,isRegionView:true,imageUrl:region.imageUrl,sourceWidth:region.width,sourceHeight:region.height,
 items:itemsInRegion(page,region).map(i=>({...i,bbox:[i.bbox[0]-x,i.bbox[1]-y,i.bbox[2]-x,i.bbox[3]-y],polygon:i.polygon?.map(([px,py])=>[px-x,py-y]) as OcrPolygon|undefined})),
 terminalPoints:page.terminalPoints?.filter(p=>p.x>=x && p.x<=right && p.y>=y && p.y<=bottom).map(p=>({...p,x:p.x-x,y:p.y-y}))}
}
export function originalPolygon(polygon:OcrPolygon,region?:RegionImage):OcrPolygon {
 return polygon.map(([x,y])=>[x+(region?.bbox[0] || 0),y+(region?.bbox[1] || 0)]) as OcrPolygon
}
