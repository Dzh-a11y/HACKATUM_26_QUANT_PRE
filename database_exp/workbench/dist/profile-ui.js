'use strict';
const profileStages={account_value:'账户估值',accounts_transform:'账户转列',market_write:'行情写入'};
const profileSources={account_value:['database_exp/stream_ingestion_cpp/accounts/calculate.cpp',61],accounts_transform:['database_exp/stream_ingestion_cpp/accounts/transform.cpp',1],market_write:['database_exp/stream_ingestion_cpp/support/db.hpp',90]};
let profileId=new URLSearchParams(location.search).get('profile')||localStorage.getItem('database-lab-profile')||null,profileData=null,profileStage='account_value',profileSort='self_pct',profileSeconds=3,profileSource='',profileChosen=Object.keys(profileStages),profileRuns=[],profileHistory=[],profileSubmitting=false,profilePolling=false,profileLoadVersion=0;
function profileRunning(){return profileSubmitting||['running','stopping'].includes(profileData?.status);}
function profileFile(stage,kind){return `/api/profile-file?id=${profileId}&stage=${stage}&kind=${kind}`;}
function compactFunction(name){
  let result='',depth=0;
  for(const c of name){if(c==='<'){if(!depth)result+='<…>';depth++;}else if(c==='>'&&depth){depth--;}else if(!depth)result+=c;}
  return result.replace(/json_abi_v[\d_]+::/g,'').replace(/\(.*$/,'(…)');
}
function functionLabel(f){return `<span class="function-name mono" title="${esc(f.name)}">${esc(compactFunction(f.name))}</span>`;}
function profilesForm(){
  const completed=profileRuns.filter(r=>r.status==='completed');
  if(!completed.some(r=>r.id===profileSource))profileSource=completed.find(r=>r.id===runId)?.id||completed[0]?.id||'';
  return `<section class="panel profile-config"><div class="section-heading"><h2>函数采样</h2><span class="chip">macOS · sample · 1 ms</span></div>
    <form id="profile-form"><div class="profile-controls"><label>数据来源<select id="profile-source" required>${completed.map(r=>`<option value="${r.id}" ${r.id===profileSource?'selected':''}>${r.id} · ${r.config.symbols} 标的 / ${r.config.teams} 团队 / ${r.config.threads} 线程预算</option>`).join('')}</select></label><label>每阶段采样 / 秒<input id="profile-seconds" type="number" min="1" max="10" value="${profileSeconds}" required></label></div>
    <div class="config-bottom"><div class="profile-checks">${Object.entries(profileStages).map(([id,title])=>`<label class="checkbox"><input type="checkbox" name="profile-stage" value="${id}" ${profileChosen.includes(id)?'checked':''}>${title}</label>`).join('')}</div><div class="actions"><button class="button secondary" type="button" id="profile-stop">停止采样</button><button class="button primary" type="submit" id="profile-start">开始采样</button></div></div></form>
    <div class="notice">重复所选输入的第 0 轮，直接调用现有 C++ 函数。每个阶段单独采样，结果用于定位函数热点；阶段总耗时仍在“数据处理流程”中查看。</div>
    <div id="profile-progress" role="status"></div></section>
    <section class="profile-record"><label>采样记录<select id="profile-history">${profileHistory.map(p=>`<option value="${p.id}" ${p.id===profileId?'selected':''}>${p.id} · ${statusNames[p.status]||p.status} · 来源 ${p.source_run}</option>`).join('')}</select></label><button type="button" class="text-button" id="profile-report">导出完整报告 ↗</button></section><div id="profile-results"></div>`;
}
function profileProgress(){
  if(serviceClosing||!$('#profile-progress'))return;
  const busy=profileRunning(),ordinaryBusy=['running','stopping'].includes(state?.job?.status);
  $('#profile-start').disabled=busy||ordinaryBusy||!profileSource;
  $('#profile-stop').disabled=!busy||profileSubmitting||profileData?.status==='stopping';
  $('#profile-history').disabled=busy;
  $('#profile-report').disabled=!profileData;
  $('#profile-progress').innerHTML=profileData?`<span class="dot ${busy?'running':'neutral'}"></span><b>${esc(statusNames[profileData.status]||profileData.status)}</b> · ${esc(profileStages[profileData.phase]||phaseNames[profileData.phase]||profileData.phase)} · 已完成 ${Object.keys(profileData.results||{}).length} / ${profileData.config.stages.length} 个阶段${profileData.error?`<div class="notice amber">${esc(profileData.error)}</div>`:''}`:'选择已有实验后开始采样。';
  renderStatus();
}
function treeNode(node,total,depth=0){
  const children=node.children||[],own=node.count-children.reduce((sum,n)=>sum+n.count,0);
  const line=`<span class="tree-percent mono">${fmt(node.count*100/total,1)}%</span>${functionLabel(node)}<span class="muted small">自身 ${count(own)} / 含子调用 ${count(node.count)}</span>`;
  return children.length?`<details class="profile-tree-node" ${depth<3?'open':''}><summary>${line}</summary><div class="profile-tree-children">${children.map(c=>treeNode(c,total,depth+1)).join('')}</div></details>`:`<div class="profile-tree-leaf">${line}</div>`;
}
function profileResults(){
  if(!profileData)return empty('还没有函数采样。');
  const results=profileData.results||{},ids=Object.keys(results);
  if(!ids.includes(profileStage))profileStage=ids[0]||profileStage;
  const result=results[profileStage],config=profileData.source_config;
  const context=config?`<p class="muted small">报告 ${esc(profileData.id)} · 输入 ${esc(profileData.source_run)} · ${count(config.symbols)} 标的 · ${count(config.teams)} 团队 · DuckDB 线程预算 ${config.threads}</p>`:'';
  const tabs=`<div class="profile-tabs">${Object.entries(profileStages).map(([id,title])=>`<button class="button ${profileStage===id?'primary':'secondary'}" data-profile-stage="${id}" ${!results[id]?'disabled':''}>${title}${results[id]?` <span>${count(results[id].stage_samples)} 样本</span>`:''}</button>`).join('')}</div>`;
  if(!result)return `<section class="panel">${context}${tabs}${empty(profileRunning()?'正在采样，完成的阶段会依次显示。':'本次没有可用的阶段样本。')}${profileData.error?Object.keys(profileStages).map(s=>`<a href="${profileFile(s,'sampler.log')}">${profileStages[s]}采样日志</a> `).join(''):''}</section>`;
  const functions=[...result.functions].sort((a,b)=>b[profileSort]-a[profileSort]),source=profileSources[profileStage];
  return `<section class="panel">${context}${tabs}
    <div class="profile-summary"><div><span class="muted small">阶段栈样本</span><strong>${count(result.stage_samples)}</strong></div><div><span class="muted small">请求采样时长</span><strong>${result.requested_seconds}<small> 秒</small></strong></div><div><span class="muted small">重复调用次数</span><strong>${count(result.worker.calls)}</strong></div><div><span class="muted small">每次处理行数</span><strong>${count(result.worker.rows_per_call)}</strong></div></div>
    <div class="notice">自身：栈顶停在该函数的样本占比；含子调用：调用栈经过该函数的占比，不能相加。只统计阶段标记内的主线程样本，包含等待，不能当作精确 CPU 时间或单次调用耗时。${profileStage==='market_write'?' 写入沿用原表约束；事务开始和回滚在阶段外，不包含提交、归档及后台线程成本。':''}</div>
    <div class="section-heading profile-table-head"><h2>函数占比</h2><label>排序<select id="profile-sort"><option value="self_pct" ${profileSort==='self_pct'?'selected':''}>函数自身占比</option><option value="inclusive_pct" ${profileSort==='inclusive_pct'?'selected':''}>含子调用占比</option></select></label></div>
    <div class="table-wrap profile-functions"><table><thead><tr><th>函数 / 所属库</th><th class="num">自身占比</th><th class="num">含子调用</th><th class="num">自身样本</th><th class="num">含子调用样本</th></tr></thead><tbody>${functions.map(f=>`<tr><td>${functionLabel(f)}<span class="muted small function-library">${esc(f.image)}</span></td><td class="num"><span class="profile-bar"><span style="width:${f.self_pct}%"></span></span>${fmt(f.self_pct,1)}%</td><td class="num">${fmt(f.inclusive_pct,1)}%</td><td class="num">${count(f.self_samples)}</td><td class="num">${count(f.inclusive_samples)}</td></tr>`).join('')}</tbody></table></div>
    <div class="profile-links"><button class="text-button" data-source="${source[0]}" data-line="${source[1]}">查看对应源码 ↗</button><a href="${profileFile(profileStage,'sample.txt')}">原始 sample 报告 ↗</a><a href="${profileFile(profileStage,'folded')}">折叠栈文件 ↗</a></div>
    <details class="profile-tree"><summary>展开阶段调用树 <span class="muted small">占比以当前阶段的全部样本为分母</span></summary><div class="profile-tree-scroll">${result.tree.map(n=>treeNode(n,result.stage_samples)).join('')}</div></details>
    <details class="profile-provenance"><summary>构建与输入证据</summary><p class="muted small">开启优化并保留调试符号和栈帧。内联函数可能合并到调用者；名称悬停可查看完整 C++ 签名。</p><pre class="code json-block">${esc(JSON.stringify({compiler:profileData.provenance?.compiler,flags:profileData.provenance?.flags,fixture_sha256:profileData.provenance?.fixture_sha256,binary_sha256:profileData.provenance?.binary_sha256,command:profileData.provenance?.command_template,source_hashes:profileData.provenance?.source_hashes},null,2))}</pre></details>
  </section>`;
}
async function loadProfiles(){
  const version=++profileLoadVersion;
  const [runs,profiles]=await Promise.all([api('/api/runs'),api('/api/profiles')]);
  if(serviceClosing||view!=='profiles'||version!==profileLoadVersion)return;
  profileRuns=runs;profileHistory=profiles;
  if(!profileHistory.some(p=>p.id===profileId))profileId=profileHistory[0]?.id||null;
  profileData=profileId?await api('/api/profile?id='+profileId):null;
  if(profileId)localStorage.setItem('database-lab-profile',profileId);
  if(!profileSource&&profileData?.source_run)profileSource=profileData.source_run;
  if(serviceClosing||view!=='profiles'||version!==profileLoadVersion)return;
  $('#content').innerHTML=profilesForm();profileProgress();$('#profile-results').innerHTML=profileResults();
}
async function pollProfile(){
  if(serviceClosing||!profileId||profilePolling||!profileRunning())return;
  profilePolling=true;
  try{
    const id=profileId,data=await api('/api/profile?id='+id);
    if(serviceClosing||id!==profileId)return;
    const changed=JSON.stringify(data)!==JSON.stringify(profileData);profileData=data;
    if(view==='profiles'&&$('#profile-results')){profileProgress();if(changed)$('#profile-results').innerHTML=profileResults();}
    if(!profileRunning()){renderStatus();if(view==='profiles')await loadProfiles();}
  }catch(e){error(e.message);}finally{profilePolling=false;}
}
document.addEventListener('submit',async event=>{
  if(event.target.id!=='profile-form')return;
  event.preventDefault();
  profileSource=event.target.querySelector('#profile-source').value;
  profileSeconds=Number(event.target.querySelector('#profile-seconds').value);
  profileChosen=[...event.target.querySelectorAll('input[name="profile-stage"]:checked')].map(x=>x.value);
  error('');profileSubmitting=true;profileProgress();
  try{
    const value=await api('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_run:profileSource,seconds:profileSeconds,stages:profileChosen})});
    profileId=value.id;profileData=await api('/api/profile?id='+profileId);
    await loadProfiles();
  }catch(e){error(e.message);}finally{profileSubmitting=false;profileProgress();}
});
document.addEventListener('change',async event=>{
  const target=event.target;
  if(target.id==='profile-source')profileSource=target.value;
  if(target.id==='profile-seconds')profileSeconds=Number(target.value);
  if(target.name==='profile-stage')profileChosen=[...document.querySelectorAll('input[name="profile-stage"]:checked')].map(x=>x.value);
  if(target.id==='profile-sort'){profileSort=target.value;$('#profile-results').innerHTML=profileResults();}
  if(target.id==='profile-history'){profileId=target.value;try{await loadProfiles();}catch(e){error(e.message);}}
});
document.addEventListener('click',async event=>{
  const target=event.target.closest('button');if(!target)return;
  if(target.dataset.profileStage){profileStage=target.dataset.profileStage;$('#profile-results').innerHTML=profileResults();}
  if(target.id==='profile-stop'){
    try{await api('/api/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:profileId})});profileData.status='stopping';profileProgress();}catch(e){error(e.message);}
  }
  if(target.id==='profile-report'&&profileData){
    const url=URL.createObjectURL(new Blob([JSON.stringify(profileData,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='database-profile-'+profileId+'.json';a.click();URL.revokeObjectURL(url);
  }
});
setInterval(pollProfile,1000);
