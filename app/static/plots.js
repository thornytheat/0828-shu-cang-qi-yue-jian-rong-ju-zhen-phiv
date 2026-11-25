import {element} from './client.js';

function block(target,className,content) {
  const node=element('div',content,{class:className});
  target.append(node);
  return node;
}

export function visualize(report,selected) {
  const target=document.querySelector('#visual');
  target.replaceChildren();
  const measurement=report.cases?.find(row=>row.case===selected)?.measure;
  if (!measurement) {block(target,'chart-note','选择有计算值的分组');return;}
  const e=measurement.evidence;

  for(const [heading,values] of [['通过',e.compatible],['差异',e.violations]]) {
    const band=block(target,'field-chips',heading);
    for(const [field,reason] of Object.entries(values)) block(band,'field-chip',`#${field} · ${Array.isArray(reason)?reason.join(' / '):reason}`);
  }
}
