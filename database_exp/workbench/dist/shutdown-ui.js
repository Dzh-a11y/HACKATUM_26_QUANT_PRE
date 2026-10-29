'use strict';
$('#shutdown').addEventListener('click',async()=>{
  if(serviceClosing)return;
  serviceClosing=true;
  const button=$('#shutdown');button.disabled=true;button.textContent='正在关闭…';
  try{
    await api('/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  }catch(e){
    serviceClosing=false;button.disabled=false;button.textContent='关闭实验台';error('关闭请求未能确认：'+e.message);renderStatus();return;
  }
  document.querySelectorAll('button,input,select').forEach(control=>control.disabled=true);
  view='closed';
  $('#error').hidden=true;$('.runbar').hidden=true;$('.run-status').hidden=true;
  $('#page-title').textContent='关闭实验台';$('#page-description').textContent='正在停止当前任务并退出本地服务。';
  $('#connection').textContent='正在关闭';$('#connection').previousElementSibling.className='dot neutral';
  $('#content').innerHTML='<section class="panel shutdown-result" role="status"><h2 id="shutdown-state">正在关闭实验台…</h2><p>正在停止实验和采样进程。已保存的实验记录保留在本机。</p><p class="muted small">再次使用时，重新运行 <code>sh database_exp/workbench/launch.sh</code>，然后刷新此页面。</p></section>';
  // Continue only this bounded shutdown check; normal experiment polling is suspended.
  for(let attempt=0;attempt<30;attempt++){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),1000);
    try{
      await fetch('/api/status',{cache:'no-store',signal:controller.signal});
    }catch(e){
      if(e.name!=='AbortError'){
        $('#shutdown-state').textContent='实验台已关闭';$('#connection').textContent='已关闭';button.textContent='已关闭';
        $('#page-description').textContent='本地服务已断开，可以关闭此页面。';return;
      }
    }finally{clearTimeout(timer);}
    await new Promise(resolve=>setTimeout(resolve,500));
  }
  $('#shutdown-state').textContent='已请求关闭，尚未确认服务退出';
});
