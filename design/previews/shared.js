const icons={
 plus:'<path d="M8 3v10M3 8h10"/>', board:'<rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="M5.5 5h3v3h3M5.5 8v3M8 11h3"/>',
 layers:'<path d="m8 2 6 3-6 3-6-3 6-3Z"/><path d="m2 8 6 3 6-3M2 11l6 3 6-3"/>',wave:'<path d="M1 9h3l2-5 3 9 2-6h4"/>',
 report:'<path d="M4 1.5h6l3 3v10H4zM10 1.5v3h3M6 8h5M6 11h5"/>',box:'<rect x="2" y="4" width="12" height="10" rx="1.5"/><path d="M5 4V2h6v2M2 8h12"/>',
 arrow:'<path d="m6 3 5 5-5 5"/>',download:'<path d="M8 2v8m-3-3 3 3 3-3M3 11v3h10v-3"/>',play:'<path d="m5 3 8 5-8 5Z"/>',
 check:'<path d="m3 8 3 3 7-7"/>', warning:'<path d="m8 2 6 11H2L8 2Z"/><path d="M8 6v3m0 2h.01"/>',
 link:'<path d="M7 4h4a3 3 0 0 1 0 6H9M9 12H5a3 3 0 0 1 0-6h2M5 8h6"/>',gear:'<path d="M6.5 2h3l.5 2 2 1 2-.2 1 2.4-1.4 1.4.1 2-1.7 1.7-2-.3-1.5 1.6-2.4-1 .1-2-1.2-1.8-2-.4v-3l2-.5 1-2z"/><circle cx="8" cy="8" r="2"/>',more:'<circle cx="3" cy="8" r=".7"/><circle cx="8" cy="8" r=".7"/><circle cx="13" cy="8" r=".7"/>',folder:'<path d="M2 4V2.5h5L9 4h5v9H2z"/>',cursor:'<path d="m3 2 10 7-5 .5L6 14 3 2Z"/>',eye:'<path d="M1 8s2.5-4 7-4 7 4 7 4-2.5 4-7 4-7-4-7-4Z"/><circle cx="8" cy="8" r="2"/>'};
const icon=(name)=>`<svg class="icon" viewBox="0 0 16 16" aria-hidden="true">${icons[name]||icons.board}</svg>`;
const theme=document.body.dataset.theme||'a';
const styles={a:{title:'极简工作台',detail:'接近 Codex · 黑白灰 · 内容优先'},b:{title:'专业工程布局',detail:'紧凑工具栏 · 对象树 · 参数密度'},c:{title:'轻盈 macOS 风格',detail:'窄图标栏 · 疏朗留白 · 聚焦画布'}};
const navItem=(name,label,count='',active=false)=>`<button class="${active?'active':''}" data-nav="${label}" title="${label}" aria-label="${label}">${icon(name)}<span class="label">${label}</span>${count?`<span class="count">${count}</span>`:''}</button>`;
const selectPads=(selected)=>['J1.1 · +3V3','J1.2 · GND','U1.1 · +3V3','U1.2 · GND'].map(s=>`<option${s.startsWith(selected)?' selected':''}>${s}</option>`).join('');
document.getElementById('root').innerHTML=`
<div class="app theme-${theme}">
 <aside class="sidebar">
  <div><a class="brand" href="index.html" title="返回风格比较"><img src="assets/ceda-icon.png" alt="Ceda 图标"><span class="brand-text">Ceda <small>0.1</small></span></a><button class="new-project" data-message="当前为视觉预览；选择风格后接入实际项目操作。">${icon('plus')}新建项目</button></div>
  <div><div class="section-label">工作空间</div><nav class="nav" aria-label="工作空间">${navItem('board','板卡概览')}${navItem('wave','供电分析','1',true)}${navItem('layers','叠层与材料')}${navItem('box','器件模型')}${navItem('report','分析报告')}</nav></div>
  <div class="projects"><div class="section-label">项目 <span>＋</span></div><div class="project-item current"><span class="dot"></span>MCU 控制板 <small>演示</small></div><div class="project-item"><span class="dot"></span>未导入其他项目</div></div>
  <div class="object-tree"><div class="section-label">板卡对象</div><div class="branch">F.Cu</div><div class="branch selected">+3V3 · 供电网络</div><div class="branch">GND · 回流网络</div><div class="branch">J1 · 电源输入</div><div class="branch">U1 · MCU 负载</div></div>
  <div class="sidebar-bottom"><span class="avatar">JY</span><span class="profile-name">本地工作空间</span></div>
 </aside>
 <main class="main">
  <header class="topbar"><div class="breadcrumb"><span>项目</span><span>／</span><span class="current">MCU 控制板</span>${icon('arrow')}<span>供电分析</span></div><div class="top-actions"><button class="button quiet" data-dialog="导入板卡">${icon('plus')}导入板卡</button><button class="button" data-dialog="工况配置">${icon('gear')}工况</button><button class="button primary" data-dialog="演示分析报告">${icon('download')}导出报告</button></div></header>
  <div class="command-strip"><span>${icon('cursor')}选择</span><span>${icon('eye')}显示对象</span><span>${icon('layers')}铜层</span><span>${icon('link')}连接检查</span><span>${icon('wave')}DC 求解</span></div>
  <div class="work-area">
   <section class="canvas-column" aria-label="板卡分析画布">
    <div class="page-heading"><div><h1>供电完整性</h1><div class="meta"><span>demo.kicad_pcb</span><span class="separator">·</span><span>2 层 PCB</span><span class="separator">·</span><span>3.3 V 电源</span><span class="tag">演示数据</span></div></div><div class="heading-right">${icon('check')}已保存 ${icon('more')}</div></div>
    <div class="canvas-toolbar"><div class="view-tabs" role="tablist" aria-label="分析视图"><button class="active" data-view="current" role="tab" aria-selected="true">电流密度</button><button data-view="voltage" role="tab" aria-selected="false">电压分布</button><button data-view="geometry" role="tab" aria-selected="false">铜层几何</button></div><span class="spacer"></span><select class="small-select" id="layer" aria-label="铜层"><option>F.Cu</option><option>B.Cu</option></select><button class="button quiet square" data-message="已适应画布" id="fit" aria-label="适应画布">${icon('eye')}</button></div>
    <div class="canvas-frame"><div class="canvas-label"><span class="dot"></span><span id="canvas-caption">F.Cu / +3V3, GND</span></div><img class="board-image" id="board" src="assets/board-current.svg" alt="来自 Ceda 演示算例的实际电流密度图"><div class="axis"><span>↗ Y</span><span>→ X</span><span>mm</span></div><div class="canvas-controls"><button id="minus" aria-label="缩小画布">−</button><span id="zoom">100%</span><button id="plus" aria-label="放大画布">＋</button></div></div>
    <div class="scale"><span id="scale-label">电流密度 / A·mm⁻²</span><div class="key"><span id="scale-min">0</span><span class="bar"><i></i><i></i><i></i><i></i><i></i></span><span id="scale-max">50.38</span></div><span>局部峰值需结合温升判断</span></div>
    <section class="results" aria-label="负载端供电结果"><div class="results-title"><h2>负载端供电</h2><a href="#" data-dialog="演示分析报告">查看详细报告 ↗</a></div><table><thead><tr><th class="table-pad">负载 / 引脚</th><th>工作电流</th><th>本地 VDD–GND</th><th>最低要求</th><th>判定</th></tr></thead><tbody><tr><td class="table-pad"><strong>U1 · MCU</strong><br><span class="muted">U1.1 → U1.2</span></td><td>0.500 A</td><td><strong class="mono">3.292066 V</strong></td><td class="muted">3.295 V</td><td><span class="status-pill">${icon('warning')}低于设定值</span></td></tr></tbody></table></section>
   </section>
   <aside class="inspector" aria-label="分析工况与属性">
    <div class="inspector-title">分析工况 <span>DC / 稳态</span></div>
    <section class="section"><h3>${icon('link')}电源端口</h3><div class="field-row"><label for="source-p">正极焊盘</label><div class="input-unit"><select id="source-p">${selectPads('J1.1')}</select></div></div><div class="field-row"><label for="source-n">回流焊盘</label><div class="input-unit"><select id="source-n">${selectPads('J1.2')}</select></div></div><div class="two-fields"><div class="field-row"><label for="voltage">源电压</label><div class="input-unit"><input id="voltage" type="number" step="0.1" value="3.3" min="0"><span>V</span></div></div><div class="field-row"><label for="current">负载电流</label><div class="input-unit"><input id="current" type="number" step="0.1" value="0.5" min="0"><span>A</span></div></div></div></section>
    <section class="section"><h3>${icon('layers')}网格与材料</h3><div class="kv"><span>铜厚</span><span>0.035 mm</span></div><div class="kv"><span>环境温度</span><span>25 °C</span></div><div class="kv"><span>网格尺度</span><span>0.50 → 0.25 mm</span></div><label class="check"><input type="checkbox" checked>使用细化网格复核</label></section>
    <section class="section"><h3>${icon('check')}计算质量</h3><div class="kv"><span>网格节点</span><span>3,617</span></div><div class="kv"><span>三角形单元</span><span>6,686</span></div><div class="kv"><span>铜损</span><span>3.967 mW</span></div><div class="kv"><span>网格电压差</span><span>0.050 mV</span></div><details><summary>验证范围</summary><p class="section-footnote">已检查规定工况的 DC 供电与数值质量。芯片功能、固件和实测精度仍未验证。</p></details></section>
    <div class="run-wrap"><button class="button primary" data-dialog="演示结果">${icon('play')}查看分析结果</button><p class="section-footnote">视觉交互预览 · 不启动真实求解</p></div>
   </aside>
  </div>
  <footer class="statusbar"><div class="cluster"><span><i class="status-dot"></i>本地工作空间</span><span>几何与网格已加载</span></div><div class="cluster"><span>F.Cu</span><span>演示算例 · DC</span><span>Ceda 0.1</span></div></footer>
 </main>
</div>
<div class="preview-banner"><strong>${theme.toUpperCase()} · ${styles[theme].title}</strong><a href="index.html">返回比较</a><button id="choose">喜欢这款</button></div>
<div class="toast" id="toast" role="status"></div>
<dialog id="dialog"><h2 id="dialog-title"></h2><p id="dialog-copy"></p><div class="dialog-actions"><button class="button" id="dialog-close">关闭</button></div></dialog>`;
let zoom=100,view='current';
function notify(text){const toast=document.getElementById('toast');toast.textContent=text;toast.classList.add('visible');clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>toast.classList.remove('visible'),3500);}
document.querySelectorAll('[data-message]').forEach(b=>b.addEventListener('click',()=>notify(b.dataset.message)));
document.getElementById('choose').addEventListener('click',()=>{try{localStorage.setItem('ceda-style-choice',theme)}catch{}notify(`已选 ${theme.toUpperCase()}。在聊天中回复 ${theme.toUpperCase()}，我会按这款继续修改桌面软件。`)});
document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.nav==='供电分析')return;notify(`${b.dataset.nav}：当前页面用于比较视觉风格，完整操作会在桌面软件中实现。`)}));
function updateBoard(){const layer=document.getElementById('layer').value;const b=document.getElementById('board');b.src=layer==='B.Cu'?'assets/board-empty.svg':`assets/board-${view}.svg`;document.getElementById('canvas-caption').textContent=layer==='B.Cu'?'B.Cu / 本演示未布铜':'F.Cu / +3V3, GND';document.getElementById('scale-label').textContent=view==='current'?'电流密度 / A·mm⁻²':view==='voltage'?'节点电压 / V':'保存后的实际铜几何';document.getElementById('scale-max').textContent=layer==='B.Cu'?'—':view==='current'?'50.38':view==='voltage'?'3.30':'—';}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{view=b.dataset.view;document.querySelectorAll('[data-view]').forEach(t=>{t.classList.toggle('active',t===b);t.setAttribute('aria-selected',String(t===b))});updateBoard()}));
document.getElementById('layer').addEventListener('change',updateBoard);
function setZoom(value){zoom=Math.max(50,Math.min(180,value));document.getElementById('board').style.setProperty('--board-scale',zoom/100);document.getElementById('zoom').textContent=`${zoom}%`;}
document.getElementById('plus').addEventListener('click',()=>setZoom(zoom+10));document.getElementById('minus').addEventListener('click',()=>setZoom(zoom-10));document.getElementById('fit').addEventListener('click',()=>setZoom(100));
const dialog=document.getElementById('dialog');document.querySelectorAll('[data-dialog]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();document.getElementById('dialog-title').textContent=b.dataset.dialog;document.getElementById('dialog-copy').textContent=b.dataset.dialog==='演示结果'||b.dataset.dialog==='演示分析报告'?'本页面展示 Ceda 已计算的合成板卡结果：3.3 V 电源、0.5 A 负载；负载端约 3.292066 V，低于示例门槛 3.295 V。这里不执行新的仿真；修改参数不会改写已计算结果。':'这是用于选定视觉风格的交互原型。桌面版已有导入、工况与报告功能；风格选定后会迁移这些布局与控件。';dialog.showModal()}));document.getElementById('dialog-close').addEventListener('click',()=>dialog.close());dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
