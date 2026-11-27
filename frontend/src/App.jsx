import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import ReactFlow, { Background, Controls, MiniMap } from 'reactflow';
import 'reactflow/dist/style.css';
import html2pdf from 'html2pdf.js';
import {
  FileText, Download, Play, Activity, Loader2,
  Search, Terminal, PieChart, BarChart3, Globe, Server,
  CheckCircle2, AlertTriangle, Crosshair, RotateCcw, FileCode2, Copy, Check
} from 'lucide-react';
import { getJobSummary, getJobGraph, createReconJob } from './api';
import axios from 'axios';

// Custom Markdown styling for the orange-accent dashboard.
const markdownComponents = {
  h1: ({ children }) => (
    <h2
      style={{ fontFamily: "'Syne', sans-serif" }}
      className="text-xl font-bold text-white tracking-tight mb-4 pb-2 border-b border-red-500/35"
    >
      {String(children).replace(/^\d+\.\s*/, '')}
    </h2>
  ),
  h2: ({ children }) => (
    <h2
      style={{ fontFamily: "'Syne', sans-serif" }}
      className="text-xl font-bold text-white tracking-tight mb-4 pb-2 border-b border-red-500/35"
    >
      {String(children).replace(/^\d+\.\s*/, '').split('&')[0].trim()}
    </h2>
  ),
  h3: ({ children }) => (
    <h3
      style={{ fontFamily: "'Syne', sans-serif" }}
      className="text-base font-bold text-red-400 mt-5 mb-2"
    >
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="text-sm text-neutral-200 leading-relaxed text-justify mb-3.5">
      {children}
    </p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc pl-5 space-y-2 mb-4 text-sm text-neutral-200 text-justify">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-5 space-y-2 mb-4 text-sm text-neutral-200 text-justify">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="text-sm text-neutral-200 leading-relaxed text-justify">
      {children}
    </li>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-white">{children}</strong>
  )
};

// Converts raw LLM Markdown into clean, structured HTML for Word (.doc) and PDF exports
const markdownToReportHtml = (md = '') => {
  const formatInline = (text) =>
    text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(
        /`([^`]+)`/g,
        '<code style="font-family: Consolas, monospace; background: transparent; padding: 0; border-radius: 0; font-size: 10pt; font-weight: normal; white-space: normal; overflow-wrap: anywhere; word-break: break-all;">$1</code>'
      );

  const lines = md.split('\n');
  let html = '';
  let inUl = false;
  let inOl = false;
  let inTechnicalSummary = false;
  let inSubsection = false;

  const closeLists = () => {
    if (inUl) {
      html += '</ul>\n';
      inUl = false;
    }
    if (inOl) {
      html += '</ol>\n';
      inOl = false;
    }
  };

  const closeSubsection = () => {
    closeLists();
    if (inSubsection) {
      html += '</section>\n';
      inSubsection = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      if (!inTechnicalSummary || !inSubsection) closeLists();
      continue;
    }

    if (line.startsWith('## ')) {
      closeSubsection();
      const title = line
        .replace(/^##\s*(?:\d+\.\s*)?/, '')
        .split('&')[0]
        .trim();
      inTechnicalSummary = /^technical summary$/i.test(title);
      html += `<h2 style="font-size: 15pt; font-weight: bold; color: #111111; border-bottom: 1.5px solid #f97316; padding-bottom: 4px; margin-top: 18px; margin-bottom: 10px; page-break-after: avoid; break-after: avoid; page-break-inside: avoid; break-inside: avoid;">${formatInline(title)}</h2>\n`;
    } else if (line.startsWith('### ')) {
      closeSubsection();
      html += '<section style="page-break-inside: avoid; break-inside: avoid;">\n';
      inSubsection = true;
      const subTitle = line.replace(/^###\s*/, '').trim();
      html += `<h3 style="font-size: 12.5pt; font-weight: bold; color: #c2410c; margin-top: 14px; margin-bottom: 6px; page-break-after: avoid; break-after: avoid; page-break-inside: avoid; break-inside: avoid;">${formatInline(subTitle)}</h3>\n`;
    } else if (/^[-*]\s+/.test(line)) {
      if (inOl) {
        html += '</ol>\n';
        inOl = false;
      }
      if (!inUl) {
        html += '<ul style="list-style: none; margin: 6px 0 12px; padding: 0;">\n';
        inUl = true;
      }
      const itemText = line.replace(/^[-*]\s+/, '');
      html += `<li style="list-style: none; padding-left: 16px; text-indent: -16px; font-size: 11pt; line-height: 1.5; text-align: justify; margin-bottom: 6px; page-break-inside: avoid; break-inside: avoid;"><span style="display: inline-block; width: 16px; text-indent: 0; vertical-align: baseline;">&#8226;</span>${formatInline(itemText)}</li>\n`;
    } else if (/^\d+\.\s+/.test(line)) {
      if (inUl) {
        html += '</ul>\n';
        inUl = false;
      }
      if (!inOl) {
        html += '<ol style="list-style-type: decimal; list-style-position: outside; margin: 6px 0 12px; padding-left: 22px;">\n';
        inOl = true;
      }
      const itemText = line.replace(/^\d+\.\s+/, '');
      html += `<li style="list-style-type: decimal; font-size: 11pt; line-height: 1.5; text-align: justify; margin-bottom: 6px; page-break-inside: avoid; break-inside: avoid;">${formatInline(itemText)}</li>\n`;
    } else if (inTechnicalSummary && inSubsection) {
      if (inOl) {
        html += '</ol>\n';
        inOl = false;
      }
      if (!inUl) {
        html += '<ul style="list-style: none; margin: 6px 0 12px; padding: 0;">\n';
        inUl = true;
      }
      html += `<li style="list-style: none; padding-left: 16px; text-indent: -16px; font-size: 11pt; line-height: 1.5; text-align: justify; margin-bottom: 6px; page-break-inside: avoid; break-inside: avoid;"><span style="display: inline-block; width: 16px; text-indent: 0; vertical-align: baseline;">&#8226;</span>${formatInline(line)}</li>\n`;
    } else {
      closeLists();
      html += `<p style="font-size: 11pt; line-height: 1.55; text-align: justify; margin-top: 0; margin-bottom: 10px;">${formatInline(line)}</p>\n`;
    }
  }

  closeSubsection();
  closeLists();
  return html;
};

// BloodHound-style Graph Builder (Black / White / Orange)
const buildBloodHoundGraph = (gNodes = [], gEdges = [], focusNodeId = null, searchQuery = '') => {
  if (!gNodes || gNodes.length === 0) return { rfNodes: [], rfEdges: [], activeFocusNode: null };

  // Filter out non-topology DNS_RECORD metadata nodes from the network graph canvas
  const topologyNodes = gNodes.filter((n) => n.type !== 'DNS_RECORD');
  const nodeMap = new Map(topologyNodes.map((n) => [String(n.id), n]));
  const query = searchQuery.trim().toLowerCase();

  let targetNode = focusNodeId ? nodeMap.get(String(focusNodeId)) : null;
  if (!targetNode && query) {
    targetNode =
      topologyNodes.find((n) => n.label.toLowerCase() === query) ||
      topologyNodes.find((n) => n.label.toLowerCase().includes(query));
  }

  const styleNode = (n, x, y, isFocal = false) => {
    const isDomain = n.type === 'DOMAIN';
    const isIp = n.type === 'IP_ADDRESS';
    const subnetTag = isIp && n.subnet_cidr ? ` [${n.subnet_cidr}]` : '';

    return {
      id: String(n.id),
      data: {
        label: `${isDomain ? 'TARGET' : isIp ? 'IP' : 'SUB'}: ${n.label}${subnetTag}`,
        rawNode: n
      },
      position: { x, y },
      style: {
        background: isFocal
          ? '#ea580c'
          : isDomain
          ? '#ffffff'
          : isIp
          ? '#1a1a1a'
          : '#0d0d0d',
        color: isDomain ? '#060606' : '#ffffff',
        fontWeight: isFocal || isDomain ? 'bold' : 'normal',
        border: isFocal
          ? '2px solid #fdba74'
          : isDomain
          ? '2px solid #f97316'
          : isIp && n.subnet_cidr
          ? '1.5px solid #f97316'
          : isIp
          ? '1.5px solid rgba(255,255,255,0.45)'
          : '1px solid rgba(255,255,255,0.22)',
        borderRadius: '8px',
        padding: '10px 12px',
        fontSize: '11px',
        fontFamily: "'JetBrains Mono', monospace",
        boxShadow: isFocal
          ? '0 0 22px rgba(249, 115, 22, 0.5)'
          : '0 4px 12px rgba(0, 0, 0, 0.55)',
        cursor: 'pointer'
      }
    };
  };

  // --- MODE A: BLOODHOUND RADIAL NEIGHBORHOOD FOCUS ---
  if (targetNode) {
    const tId = String(targetNode.id);
    const directEdges = gEdges.filter(
      (e) => String(e.source) === tId || String(e.target) === tId
    );

    const sortedEdges = [...directEdges]
      .sort((a, b) => {
        const rank = { C001: 1, C003: 2, C002: 3 };
        return (rank[a.rule_id] || 9) - (rank[b.rule_id] || 9);
      })
      .slice(0, 28);

    const neighborIds = [];
    const seen = new Set([tId]);
    sortedEdges.forEach((e) => {
      const otherId = String(e.source) === tId ? String(e.target) : String(e.source);
      if (!seen.has(otherId) && nodeMap.has(otherId)) {
        seen.add(otherId);
        neighborIds.push(otherId);
      }
    });

    const centerX = 520;
    const centerY = 300;
    const radius = Math.max(230, neighborIds.length * 14);

    const rfNodes = [styleNode(targetNode, centerX, centerY, true)];
    neighborIds.forEach((nId, idx) => {
      const angle = (2 * Math.PI * idx) / Math.max(neighborIds.length, 1);
      const nx = centerX + radius * Math.cos(angle);
      const ny = centerY + radius * Math.sin(angle);
      rfNodes.push(styleNode(nodeMap.get(nId), nx, ny, false));
    });

    const visibleIds = new Set(rfNodes.map((n) => n.id));
    const rfEdges = sortedEdges
      .filter((e) => visibleIds.has(String(e.source)) && visibleIds.has(String(e.target)))
      .map((e, idx) => {
        const ruleId = e.rule_id || 'C001';
        return {
          id: `focus-edge-${idx}`,
          source: String(e.source),
          target: String(e.target),
          label: `${ruleId}: ${e.relationship}`,
          labelStyle: { fill: '#ffffff', fontSize: 9, fontFamily: "'JetBrains Mono', monospace" },
          labelBgStyle: { fill: '#060606', fillOpacity: 0.92 },
          animated: ruleId === 'C001',
          style: {
            stroke:
              ruleId === 'C001'
                ? '#f97316'
                : ruleId === 'C003'
                ? '#ffffff'
                : '#737373',
            strokeWidth: 1.8
          }
        };
      });

    return { rfNodes, rfEdges, activeFocusNode: targetNode };
  }

  // --- MODE B: CLEAN IP-HUB CLUSTER OVERVIEW ---
  const c001Edges = gEdges.filter((e) => e.rule_id === 'C001');
  const ipGroups = new Map();

  c001Edges.forEach((e) => {
    const subId = String(e.source);
    const ipId = String(e.target);
    if (nodeMap.has(subId) && nodeMap.has(ipId)) {
      if (!ipGroups.has(ipId)) ipGroups.set(ipId, new Set());
      ipGroups.get(ipId).add(subId);
    }
  });

  const rfNodes = [];
  const rfEdges = [];
  const placedNodes = new Set();

  let clusterCol = 0;
  let clusterRow = 0;

  Array.from(ipGroups.entries())
    .sort((a, b) => b[1].size - a[1].size)
    .slice(0, 10)
    .forEach(([ipId, subIdSet]) => {
      const ipNode = nodeMap.get(ipId);
      const baseX = clusterCol * 560 + 240;
      const baseY = clusterRow * 380 + 190;

      if (!placedNodes.has(ipId)) {
        rfNodes.push(styleNode(ipNode, baseX, baseY, false));
        placedNodes.add(ipId);
      }

      const sliceSubs = Array.from(subIdSet).slice(0, 6);
      sliceSubs.forEach((subId, i) => {
        const angle = (2 * Math.PI * i) / Math.max(sliceSubs.length, 1) - Math.PI / 2;
        const sx = baseX + 185 * Math.cos(angle);
        const sy = baseY + 135 * Math.sin(angle);

        if (!placedNodes.has(subId)) {
          rfNodes.push(styleNode(nodeMap.get(subId), sx, sy, false));
          placedNodes.add(subId);
        }

        rfEdges.push({
          id: `hub-${subId}-${ipId}`,
          source: subId,
          target: ipId,
          label: 'C001: RESOLVES_TO',
          labelStyle: { fill: '#e5e5e5', fontSize: 8, fontFamily: "'JetBrains Mono', monospace" },
          labelBgStyle: { fill: '#060606', fillOpacity: 0.9 },
          animated: true,
          style: { stroke: '#f97316', strokeWidth: 1.5 }
        });
      });

      clusterCol++;
      if (clusterCol >= 2) {
        clusterCol = 0;
        clusterRow++;
      }
    });

  if (rfNodes.length === 0 && topologyNodes.length > 0) {
    const root = topologyNodes.find((n) => n.type === 'DOMAIN') || topologyNodes[0];
    const subs = topologyNodes.filter((n) => n.id !== root.id).slice(0, 14);
    rfNodes.push(styleNode(root, 480, 280, true));
    subs.forEach((s, i) => {
      const angle = (2 * Math.PI * i) / subs.length;
      rfNodes.push(styleNode(s, 480 + 250 * Math.cos(angle), 280 + 220 * Math.sin(angle), false));
      rfEdges.push({
        id: `root-e-${i}`,
        source: String(root.id),
        target: String(s.id),
        label: 'C002: HAS_SUBDOMAIN',
        labelStyle: { fill: '#a3a3a3', fontSize: 8, fontFamily: "'JetBrains Mono', monospace" },
        labelBgStyle: { fill: '#060606', fillOpacity: 0.9 },
        style: { stroke: '#525252' }
      });
    });
  }

  return { rfNodes, rfEdges, activeFocusNode: null };
};

const getExportGraphData = (summaryData, rawGraphData) => {
  const entities = summaryData?.entities || [];
  const fallbackNodes = entities.map((entity) => ({
    ...entity,
    id: String(entity.id),
    label: entity.value
  }));
  const fallbackEdges = entities.flatMap((entity) =>
    (entity.relationships || [])
      .filter((relationship) => relationship.target_id)
      .map((relationship) => ({
        source: String(entity.id),
        target: String(relationship.target_id),
        relationship: relationship.relationship,
        rule_id: relationship.rule_id,
        rule_description: relationship.rule_description,
        evidence_sources: relationship.evidence_sources || []
      }))
  );

  return {
    nodes: rawGraphData?.nodes?.length ? rawGraphData.nodes : fallbackNodes,
    edges: rawGraphData?.edges?.length ? rawGraphData.edges : fallbackEdges
  };
};

const csvCell = (value) => {
  const text = value == null
    ? ''
    : typeof value === 'string'
    ? value
    : JSON.stringify(value);
  const safeText = /^[\t\r\n ]*[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safeText.replace(/"/g, '""')}"`;
};

const downloadExportFile = (content, mimeType, filename) => {
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
};

export default function App() {
  const [jobId, setJobId] = useState('');
  const [targetDomain, setTargetDomain] = useState('');
  const [summaryData, setSummaryData] = useState(null);
  const [rawGraphData, setRawGraphData] = useState({ nodes: [], edges: [] });
  const [graphSearch, setGraphSearch] = useState('');
  const [focusNodeId, setFocusNodeId] = useState(null);
  const [selectedNodeInfo, setSelectedNodeInfo] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('');
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState([]);
  const [copiedLogs, setCopiedLogs] = useState(false);
  const [activeTab, setActiveTab] = useState('briefing');
  const [showIdLookup, setShowIdLookup] = useState(false);
  const [assetFilter, setAssetFilter] = useState('ALL');
  const [exportingPdf, setExportingPdf] = useState(false);

  const consoleEndRef = useRef(null);

  useEffect(() => {
    if (loading && consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, loading]);

  useEffect(() => {
    if (rawGraphData.nodes.length > 0) {
      const { rfNodes, rfEdges, activeFocusNode } = buildBloodHoundGraph(
        rawGraphData.nodes,
        rawGraphData.edges,
        focusNodeId,
        graphSearch
      );
      setNodes(rfNodes);
      setEdges(rfEdges);
      if (activeFocusNode) {
        setSelectedNodeInfo(activeFocusNode);
      }
    }
  }, [focusNodeId, graphSearch, rawGraphData]);

  const addConsoleLog = (msg, level = 'INFO') => {
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
    setLogs((prev) => [...prev, { timestamp, msg, level }]);
  };

  const handleCopyLogs = () => {
    if (logs.length === 0) return;
    const text = logs.map((l) => `[${l.timestamp}] ${l.msg}`).join('\n');
    navigator.clipboard.writeText(text);
    setCopiedLogs(true);
    setTimeout(() => setCopiedLogs(false), 2000);
  };

  useEffect(() => {
    let interval;
    if (loading) {
      interval = setInterval(() => {
        setProgress((prev) => {
          if (prev < 70) return prev + Math.floor(Math.random() * 2) + 1;
          if (prev >= 75 && prev < 95) return prev + 1;
          return prev;
        });
      }, 800);
    } else {
      setProgress(0);
    }
    return () => clearInterval(interval);
  }, [loading]);

  const splitBriefingSections = (markdownText = '') => {
    const techMatch = markdownText.search(/##\s*(?:\d+\.\s*)?Technical Summary[^\n]*/i);
    if (techMatch !== -1) {
      let execPart = markdownText.slice(0, techMatch).trim();
      let techPart = markdownText.slice(techMatch).trim();

      execPart = execPart.replace(/^##\s*\d+\.\s*Executive Summary/i, '## Executive Summary');
      techPart = techPart.replace(/^##\s*(?:\d+\.\s*)?Technical Summary[^\n]*/i, '## Technical Summary');

      return { execSummary: execPart, techSummary: techPart };
    }
    return {
      execSummary: markdownText.replace(/^##\s*\d+\.\s*Executive Summary/i, '## Executive Summary'),
      techSummary: ''
    };
  };

  const buildReportBodyHtml = () => {
    const { execSummary, techSummary } = splitBriefingSections(summaryData?.briefing_markdown || '');
    const execHtml = markdownToReportHtml(execSummary);
    const techHtml = markdownToReportHtml(techSummary);

    const entitiesRows = (summaryData.entities || [])
      .map((e) => {
        const confPct = Math.round((e.confidence || 0.6) * 100);
        return `<tr>
          <td style="border: 1px solid #cbd5e1; padding: 6px 8px; font-size: 9.5pt;">${e.type}</td>
          <td style="border: 1px solid #cbd5e1; padding: 6px 8px; font-family: Consolas, monospace; font-size: 9.5pt;">${e.value}</td>
          <td style="border: 1px solid #cbd5e1; padding: 6px 8px; font-size: 9.5pt;">${confPct}% (${e.type === 'DNS_RECORD' ? 'Authoritative' : confPct >= 80 ? 'Correlated' : 'Single-Source'})</td>
        </tr>`;
      })
      .join('');

    return `
      <div style="font-family: Calibri, Arial, sans-serif; color: #1e293b; line-height: 1.5;">
        <h1 style="font-size: 18pt; color: #111111; margin-bottom: 6px;">Passive Reconnaissance Intelligence Report</h1>
        <p style="font-size: 10.5pt; color: #475569; margin-top: 0; margin-bottom: 14px;">
          <strong>Target Domain:</strong> ${summaryData.target_domain} &nbsp;|&nbsp;
          <strong>Job ID:</strong> ${jobId}<br/>
          <strong>Total Subdomains:</strong> ${summaryData.metrics.total_subdomains} &nbsp;|&nbsp;
          <strong>Active IPs:</strong> ${summaryData.metrics.total_ips} &nbsp;|&nbsp;
          <strong>Multi-Source Validated:</strong> ${summaryData.metrics.high_confidence_count}
        </p>
        <hr style="border: none; border-top: 1px solid #cbd5e1; margin-bottom: 16px;" />
        ${execHtml}
        ${techHtml}
        <h2 style="font-size: 15pt; font-weight: bold; color: #111111; border-bottom: 1.5px solid #f97316; padding-bottom: 4px; margin-top: 22px; margin-bottom: 10px; page-break-after: avoid; break-after: avoid; page-break-inside: avoid; break-inside: avoid;">
          Discovered Subdomains, IPs &amp; DNS/WHOIS Inventory
        </h2>
        <table style="border-collapse: collapse; width: 100%; margin-top: 8px;">
          <thead>
            <tr style="background-color: #f1f5f9;">
              <th style="border: 1px solid #cbd5e1; padding: 7px 8px; text-align: left; font-size: 10pt;">Asset Type</th>
              <th style="border: 1px solid #cbd5e1; padding: 7px 8px; text-align: left; font-size: 10pt;">Discovered Host / IP / Record</th>
              <th style="border: 1px solid #cbd5e1; padding: 7px 8px; text-align: left; font-size: 10pt;">Confidence Score</th>
            </tr>
          </thead>
          <tbody>
            ${entitiesRows}
          </tbody>
        </table>
      </div>
    `;
  };

  const handleExportWord = () => {
    if (!summaryData) return;

    const htmlContent = `
      <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
      <head>
        <meta charset='utf-8'>
        <title>Recon Report - ${summaryData.target_domain}</title>
      </head>
      <body>
        ${buildReportBodyHtml()}
      </body>
      </html>
    `;

    const blob = new Blob(['\ufeff', htmlContent], { type: 'application/msword' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `recon-report-${summaryData.target_domain}.doc`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportPDF = async () => {
    if (!summaryData || exportingPdf) return;
    setExportingPdf(true);

    try {
      const container = document.createElement('div');
      container.innerHTML = buildReportBodyHtml();
      container.style.padding = '12mm';
      container.style.background = '#ffffff';
      container.style.color = '#1e293b';

      const opt = {
        margin: [10, 10, 12, 10],
        filename: `recon-report-${summaryData.target_domain}.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak: { mode: ['css', 'legacy'] }
      };

      await html2pdf().set(opt).from(container).save();
    } catch (err) {
      console.error('PDF generation error:', err);
      alert('Failed to generate PDF file.');
    } finally {
      setExportingPdf(false);
    }
  };

  const handleExportJSON = () => {
    if (!summaryData) return;
    const graph = getExportGraphData(summaryData, rawGraphData);
    const exportData = {
      schema_version: '1.0',
      job_id: jobId,
      target_domain: summaryData.target_domain,
      exported_at_utc: new Date().toISOString(),
      metrics: summaryData.metrics,
      assets: summaryData.entities || [],
      graph
    };
    const filenameTarget = summaryData.target_domain.replace(/[^a-z0-9.-]/gi, '_');
    downloadExportFile(
      JSON.stringify(exportData, null, 2),
      'application/json;charset=utf-8',
      `recon-report-${filenameTarget}.json`
    );
  };

  const handleExportCSV = () => {
    if (!summaryData) return;
    const graph = getExportGraphData(summaryData, rawGraphData);
    const columns = [
      'row_type', 'job_id', 'target_domain', 'total_subdomains', 'total_ips',
      'high_confidence_count', 'id', 'type', 'value', 'confidence',
      'resolves_to', 'relationships', 'corroborated_by', 'subnet_cidr',
      'asn', 'asn_cidr', 'provider', 'asn_country', 'asn_registry', 'asn_records',
      'asn_source', 'record_type', 'cname_target', 'cname_chain', 'service_provider',
      'service_providers', 'third_party', 'dangling', 'source', 'target',
      'relationship', 'rule_id', 'rule_description', 'evidence_sources'
    ];
    const metadata = {
      job_id: jobId,
      target_domain: summaryData.target_domain,
      total_subdomains: summaryData.metrics?.total_subdomains,
      total_ips: summaryData.metrics?.total_ips,
      high_confidence_count: summaryData.metrics?.high_confidence_count
    };
    const rows = [
      { ...metadata, row_type: 'SUMMARY' },
      ...(summaryData.entities || []).map((entity) => ({
        ...metadata,
        ...entity,
        row_type: 'ASSET'
      })),
      ...graph.nodes.map((node) => ({
        ...metadata,
        ...node,
        value: node.label,
        row_type: 'NODE'
      })),
      ...graph.edges.map((edge) => ({
        ...metadata,
        ...edge,
        row_type: 'EDGE'
      }))
    ];
    const csv = [
      columns.map(csvCell).join(','),
      ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(','))
    ].join('\r\n');
    const filenameTarget = summaryData.target_domain.replace(/[^a-z0-9.-]/gi, '_');
    downloadExportFile(
      `\ufeff${csv}`,
      'text/csv;charset=utf-8',
      `recon-report-${filenameTarget}.csv`
    );
  };

  const fetchDashboardData = async (idToFetch, isLookup = false) => {
    if (!idToFetch) return;
    if (isLookup) {
      setLogs([]);
      addConsoleLog(`[LOOKUP] Retrieving historical reconnaissance job: ${idToFetch}`, 'INFO');
    }
    setLoading(true);
    setProgress(75);
    setFocusNodeId(null);
    setGraphSearch('');
    setSelectedNodeInfo(null);
    setLoadingText(
      isLookup
        ? 'Loading saved report and correlated topology...'
        : 'Analyzing findings and preparing the report...'
    );
    if (isLookup) {
      addConsoleLog(`[REPORT] Loading stored findings and saved briefing for job ${idToFetch}.`, 'INFO');
    } else {
      addConsoleLog(
        `[AI_ENGINE] Invoking Ollama (qwen2.5) + Grounding Gate verification...`,
        'AI'
      );
    }

    try {
      const summary = await getJobSummary(idToFetch, !isLookup);
      if (summary.briefing_status === 'generated') {
        addConsoleLog(`[LLM] Analysis generated and saved for job ${idToFetch}.`, 'AI');
      } else if (summary.briefing_status === 'cached') {
        addConsoleLog(`[LLM] Loaded the saved analysis for job ${idToFetch}; no new generation was needed.`, 'INFO');
      } else if (summary.briefing_status === 'missing') {
        addConsoleLog(`[LLM] No saved analysis exists for this historical job; displaying stored findings only.`, 'WARN');
      } else if (summary.briefing_status === 'no_entities') {
        addConsoleLog(`[LLM] No findings were available to analyze for job ${idToFetch}.`, 'WARN');
      }
      setProgress(90);
      setLoadingText('Loading correlations and graph...');
      setSummaryData(summary);

      let graph = { nodes: [], edges: [] };
      try {
        graph = await getJobGraph(idToFetch);
      } catch (gErr) {
        console.warn('Graph endpoint fallback triggered', gErr);
      }

      const gNodes = graph.nodes || graph.graph?.nodes || [];
      const gEdges = graph.edges || graph.graph?.edges || [];

      if (gNodes.length > 0) {
        setRawGraphData({ nodes: gNodes, edges: gEdges });
      } else if (summary.entities && summary.entities.length > 0) {
        const fallbackNodes = [
          { id: 'root-target', label: summary.target_domain, type: 'DOMAIN', confidence: 1 },
          ...summary.entities.map((entity) => ({
            ...entity,
            id: String(entity.id),
            label: entity.value
          }))
        ];
        const fallbackEdges = summary.entities.flatMap((entity) =>
          (entity.relationships || [])
            .filter((relationship) => relationship.target_id)
            .map((relationship) => ({
              source: String(entity.id),
              target: String(relationship.target_id),
              rule_id: relationship.rule_id,
              relationship: relationship.relationship,
              rule_description: relationship.rule_description,
              evidence_sources: relationship.evidence_sources || []
            }))
        );
        setRawGraphData({ nodes: fallbackNodes, edges: fallbackEdges });
      } else {
        setRawGraphData({ nodes: [], edges: [] });
        setNodes([]);
        setEdges([]);
      }

      setJobId(idToFetch || '');
      setProgress(100);
      addConsoleLog(`[PIPELINE] Dashboard rendered successfully (${summary.metrics?.total_subdomains || 0} subdomains, ${summary.metrics?.total_ips || 0} IPs).`, 'SUCCESS');

      await new Promise((r) => setTimeout(r, 300));
    } catch (err) {
      console.error('Error fetching job data', err);
      addConsoleLog(`[ERROR] Failed to retrieve dashboard data: ${err.message}`, 'ERROR');
      alert(`Could not fetch data for Job ID: ${idToFetch}. Verify backend API status.`);
    } finally {
      setLoading(false);
      setLoadingText('');
      setProgress(0);
    }
  };

  const pollJobStatus = async (id) => {
    const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    let attempts = 0;
    const maxAttempts = 60;
    let lastLoggedStatus = '';

    while (attempts < maxAttempts) {
      let res;
      try {
        res = await axios.get(`${API_BASE}/api/v1/jobs/${id}/status`);
      } catch (err) {
        addConsoleLog(`[WARN] Polling retry: ${err.message}`, 'WARN');
        await new Promise((r) => setTimeout(r, 3000));
        attempts++;
        continue;
      }

      const status = res.data?.status?.toUpperCase();
      if (status !== lastLoggedStatus) {
        lastLoggedStatus = status;
        addConsoleLog(`[JOB_STATUS] Backend reported state: ${status || 'RUNNING'}`, 'INFO');
      }

      if (status === 'COMPLETED' || status === 'PARTIAL_SUCCESS') {
        if (status === 'PARTIAL_SUCCESS') {
          addConsoleLog(`[OSINT_MODULES] Scan completed with partial output.`, 'WARN');
        } else {
          addConsoleLog(`[OSINT_MODULES] All 6 passive collectors completed successfully.`, 'SUCCESS');
        }
        addConsoleLog(`[CORRELATION] Loading stored relationships and correlated topology (C001-C005)...`, 'INFO');
        setProgress(75);
        return true;
      }
      if (status === 'FAILED') {
        addConsoleLog(`[FATAL] Job execution failed on backend worker.`, 'ERROR');
        throw new Error('Recon job failed on the backend.');
      }

      if (attempts === 2) addConsoleLog(`[MODULE: Subfinder] Enumerating passive DNS & CT logs...`, 'EXEC');
      if (attempts === 4) addConsoleLog(`[MODULE: DnsAuth & WHOIS] Querying SPF/DMARC/MX & registrar records...`, 'EXEC');
      if (attempts === 6) addConsoleLog(`[MODULE: Amass] Mapping passive ASN & subdomain space...`, 'EXEC');
      if (attempts === 8) addConsoleLog(`[MODULE: theHarvester] Querying passive search & certificate APIs...`, 'EXEC');
      if (attempts === 11) addConsoleLog(`[MODULE: Waybackurls] Extracting historical web archive endpoints...`, 'EXEC');

      setLoadingText(`Recon status: ${status || 'RUNNING'} (${attempts * 3}s elapsed)...`);
      await new Promise((r) => setTimeout(r, 3000));
      attempts++;
    }

    throw new Error('Job execution status polling timed out.');
  };

  const handleStartScan = async (e) => {
    e.preventDefault();
    if (!targetDomain.trim()) return;

    setLoading(true);
    setProgress(5);
    setLogs([]);
    setActiveTab('briefing');
    setLoadingText(`Initializing reconnaissance job for ${targetDomain}...`);
    setSummaryData(null);

    addConsoleLog(`[SYSTEM] Initializing scan sequence for domain: ${targetDomain.trim()}`, 'INFO');

    try {
      const res = await createReconJob(targetDomain.trim());
      const newJobId = res?.id || res?.job_id || '';

      if (!newJobId) {
        alert('Failed to extract Job ID from backend response.');
        setLoading(false);
        return;
      }

      setJobId(newJobId);
      setProgress(15);
      addConsoleLog(`[API] Job enqueued with UUID: ${newJobId}`, 'SUCCESS');

      await pollJobStatus(newJobId);
      await fetchDashboardData(newJobId, false);
    } catch (err) {
      console.error('Error starting recon job', err);
      addConsoleLog(`[FATAL] Execution halted: ${err.message}`, 'ERROR');
      alert(`Scan failed: ${err.message || 'Ensure FastAPI backend is active.'}`);
      setLoading(false);
      setLoadingText('');
      setProgress(0);
    }
  };

  const totalSubdomains = summaryData?.metrics?.total_subdomains || 0;
  const totalIps = summaryData?.metrics?.total_ips || 0;
  const totalAssets = Math.max(totalSubdomains + totalIps, 1);
  const subPct = Math.round((totalSubdomains / totalAssets) * 100);
  const ipPct = 100 - subPct;

  const assetEntities = (summaryData?.entities || []).filter((e) => e.type !== 'DNS_RECORD');
  const highConfCount =
    assetEntities.filter((e) => (e.confidence || 0) >= 0.8).length ||
    (summaryData?.metrics?.high_confidence_count || 0);
  const lowConfCount = Math.max(totalAssets - highConfCount, 0);
  const highConfPct = Math.round((highConfCount / totalAssets) * 100);
  const lowConfPct = 100 - highConfPct;

  const { execSummary, techSummary } = splitBriefingSections(summaryData?.briefing_markdown || '');
  const hasGroundingWarning = (summaryData?.briefing_markdown || '').includes('Grounding Gate Audit Warning');

  const filteredEntities = (summaryData?.entities || []).filter((item) => {
    if (assetFilter === 'ALL') return true;
    return item.type === assetFilter;
  });

  const searchSuggestions = graphSearch.trim()
    ? rawGraphData.nodes
        .filter((n) => n.type !== 'DNS_RECORD' && n.label.toLowerCase().includes(graphSearch.trim().toLowerCase()))
        .slice(0, 6)
    : [];

  const selectedNodeEdges = selectedNodeInfo
    ? rawGraphData.edges.filter(
        (e) =>
          String(e.source) === String(selectedNodeInfo.id) ||
          String(e.target) === String(selectedNodeInfo.id)
      )
    : [];

  const glassStyle = {
    background: 'rgba(255, 255, 255, 0.03)',
    backdropFilter: 'blur(12px)',
    WebkitBackdropFilter: 'blur(12px)',
    boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 8px 24px rgba(0, 0, 0, 0.45)'
  };

  return (
    <div
      style={{ fontFamily: "'JetBrains Mono', monospace", backgroundColor: '#060606' }}
      className="app-shell min-h-screen text-neutral-100 flex flex-col relative overflow-x-hidden"
    >
      {/* Subtle orange and white glass ambient glow on #060606 */}
      <div
        className="pointer-events-none fixed inset-0 z-0"
        style={{
          background:
            'radial-gradient(circle at 50% 18%, rgba(249, 115, 22, 0.12), transparent 45%), radial-gradient(circle at 12% 85%, rgba(255, 255, 255, 0.04), transparent 40%)'
        }}
      />

      {/* Top glass header */}
      <header
        className="app-header sticky top-0 z-30 border-b border-white/10 px-6 py-3.5 flex items-center justify-between gap-4 print:hidden"
        style={{
          background: 'rgba(6, 6, 6, 0.85)',
          backdropFilter: 'blur(16px)'
        }}
      >
        <a
          href="/"
          onClick={(event) => {
            event.preventDefault();
            window.history.replaceState(
              null,
              '',
              `${window.location.pathname}${window.location.search}`
            );
            window.location.reload();
          }}
          className="app-brand-link flex items-center gap-3 shrink-0"
          aria-label="Return to the default page"
        >
          <div className="brand-mark shrink-0" aria-hidden="true">
            <img src="/favicon.svg" alt="" />
          </div>
          <div>
            <h1
              className="app-brand-title text-lg tracking-tight text-white leading-tight whitespace-nowrap"
            >
              Passive Recon <span className="text-red-500">Intelligence</span>
            </h1>
          </div>
        </a>

        <div className="flex items-center gap-3 flex-wrap justify-end">
          <a
            href="https://github.com/bobjianxiang/Passive-Recon-Intelligence"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs bg-white/[0.03] hover:bg-white/[0.08] border border-white/15 hover:border-red-500/50 px-3 py-1.5 rounded-lg text-white transition whitespace-nowrap"
          >
            GitHub
          </a>
          {showIdLookup ? (
            <div className="flex items-center gap-2 bg-neutral-950 p-1.5 rounded-lg border border-red-500/40">
              <input
                type="text"
                placeholder="Paste Job ID..."
                value={jobId || ''}
                onChange={(e) => setJobId(e.target.value)}
                className="bg-transparent text-xs px-2 py-1 focus:outline-none w-60 text-white font-mono"
              />
              <button
                onClick={() => fetchDashboardData(jobId, true)}
                disabled={loading || !jobId.trim()}
                className="bg-red-600 hover:bg-red-500 disabled:opacity-50 text-xs px-2.5 py-1 rounded text-white font-semibold flex items-center gap-1 transition cursor-pointer"
              >
                <Activity className="h-3 w-3" /> Fetch
              </button>
              <button onClick={() => setShowIdLookup(false)} className="text-xs text-neutral-400 hover:text-white px-1 cursor-pointer">
                ✕
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowIdLookup(true)}
              className="text-xs bg-white/[0.03] hover:bg-white/[0.08] border border-white/15 hover:border-red-500/50 px-3 py-1.5 rounded-lg text-white flex items-center gap-1.5 transition cursor-pointer whitespace-nowrap"
            >
              <Search className="h-3.5 w-3.5 text-red-500" /> Lookup by Job ID
            </button>
          )}

          {summaryData && (
            <div className="flex flex-wrap items-center justify-end gap-2 border-l border-white/15 pl-3">
              <button
                onClick={handleExportCSV}
                className="bg-white/[0.04] hover:bg-white/[0.1] text-white text-xs font-medium px-2.5 py-1.5 rounded-lg border border-white/15 flex items-center gap-1.5 cursor-pointer transition whitespace-nowrap"
              >
                <FileText className="h-3.5 w-3.5 text-neutral-300" /> CSV
              </button>
              <button
                onClick={handleExportJSON}
                className="bg-white/[0.04] hover:bg-white/[0.1] text-white text-xs font-medium px-2.5 py-1.5 rounded-lg border border-white/15 flex items-center gap-1.5 cursor-pointer transition whitespace-nowrap"
              >
                <FileCode2 className="h-3.5 w-3.5 text-neutral-300" /> JSON
              </button>
              <button
                onClick={handleExportPDF}
                disabled={exportingPdf}
                className="bg-red-600/20 hover:bg-red-600/35 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg border border-red-500/50 flex items-center gap-1.5 cursor-pointer transition whitespace-nowrap"
              >
                {exportingPdf ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-red-400" />
                ) : (
                  <Download className="h-3.5 w-3.5 text-red-400" />
                )}
                {exportingPdf ? 'Generating PDF...' : 'Download PDF'}
              </button>
              <button
                onClick={handleExportWord}
                className="bg-white/[0.04] hover:bg-white/[0.1] text-white text-xs font-medium px-3 py-1.5 rounded-lg border border-white/15 flex items-center gap-1.5 cursor-pointer transition whitespace-nowrap"
              >
                <FileText className="h-3.5 w-3.5 text-neutral-300" /> Word (.doc)
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Container */}
      <main className="app-main flex-1 p-6 flex flex-col gap-6 max-w-7xl mx-auto w-full relative z-10">
        {/* Landing page and scan form */}
        {!summaryData && !loading && (
          <div className="landing-page">
            <section id="home" className="landing-hero">
              <div className="landing-hero-copy">
                <h2 className="landing-title" style={{ fontFamily: "'Syne', sans-serif" }}>
                  Passive Recon <span className="text-orange-400">Intelligence</span>
                </h2>
                <p className="landing-tagline">Zero-touch OSINT · AI-powered security analysis</p>
                <p className="landing-description">
                  Discover and correlate public-facing assets with passive collection, an evidence-grounded report, and an interactive relationship graph.
                </p>
                <div className="landing-actions">
                  <a className="landing-button landing-button-primary" href="#target-scan">
                    Start scanning
                    <span aria-hidden="true">→</span>
                  </a>
                  <a
                    className="landing-button"
                    href="https://github.com/bobjianxiang/Passive-Recon-Intelligence"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Documentation
                  </a>
                </div>
              </div>

              <div className="landing-terminal glass-card" aria-label="Recon workflow preview">
                <div className="landing-terminal-heading">
                  <span className="landing-terminal-dot" />
                  <span>RECON WORKFLOW</span>
                  <span className="landing-terminal-status">READY</span>
                </div>
                <div className="landing-terminal-lines">
                  <p><span>&gt;</span> POST /api/v1/jobs</p>
                  <p><span>&gt;</span> target_domain: [domain]</p>
                  <p><span>&gt;</span> Queueing six passive collectors...</p>
                  <p><span>&gt;</span> Correlating findings and preparing the grounded report...</p>
                  <p className="landing-terminal-ready"><span>&gt;</span> Ready. Enter a target to begin.<i /></p>
                </div>
              </div>
            </section>

            <section id="target-scan" className="landing-section landing-scan-section">
              <div className="landing-section-heading">
                <span className="landing-eyebrow">01 / NEW RECON JOB</span>
                <h3 style={{ fontFamily: "'Syne', sans-serif" }}>Choose a target</h3>
                <p>Enter a domain to start a scan and build its intelligence dashboard.</p>
              </div>
              <div className="landing-scan-card glass-card">
                <form onSubmit={handleStartScan} className="landing-scan-form">
                  <label htmlFor="landing-target">Target domain</label>
                  <div className="landing-scan-controls">
                    <input
                      id="landing-target"
                      type="text"
                      placeholder="example.com"
                      value={targetDomain || ''}
                      onChange={(e) => setTargetDomain(e.target.value)}
                      className="landing-input"
                    />
                    <button
                      type="submit"
                      disabled={!targetDomain.trim()}
                      className="landing-button landing-button-primary"
                    >
                      <Play className="h-4 w-4" /> Run target scan
                    </button>
                  </div>
                </form>
              </div>
            </section>

            <section id="capabilities" className="landing-section landing-capabilities">
              <div className="landing-section-heading">
                <span className="landing-eyebrow">02 / PLATFORM</span>
                <h3 style={{ fontFamily: "'Syne', sans-serif" }}>Capabilities</h3>
              </div>
              <div className="landing-features-grid">
                {[
                  {
                    number: '01',
                    title: 'Passive asset discovery',
                    description: 'Collect public subdomain, IP, DNS, and WHOIS intelligence through the existing recon pipeline.'
                  },
                  {
                    number: '02',
                    title: 'Evidence-grounded analysis',
                    description: 'Review an AI-generated intelligence report with its grounding status and collected evidence.'
                  },
                  {
                    number: '03',
                    title: 'Correlated asset graph',
                    description: 'Explore discovered entities and their relationships in an interactive topology view.'
                  },
                  {
                    number: '04',
                    title: 'Confidence scoring',
                    description: 'See confidence levels and multi-source corroboration alongside discovered assets.'
                  },
                  {
                    number: '05',
                    title: 'Live execution logs',
                    description: 'Follow scan progress and inspect or copy the recorded pipeline events.'
                  },
                  {
                    number: '06',
                    title: 'Exportable reports',
                    description: 'Download completed intelligence reports as PDF or Word documents.'
                  }
                ].map((feature) => (
                  <article key={feature.number} className="landing-feature-card glass-card">
                    <span className="landing-feature-number">{feature.number}</span>
                    <h4 style={{ fontFamily: "'Syne', sans-serif" }}>{feature.title}</h4>
                    <p>{feature.description}</p>
                  </article>
                ))}
              </div>
            </section>

            <footer className="landing-footer">
              <span>Passive Recon Intelligence · Passive OSINT toolkit</span>
              <span>Reports, asset graph, and execution logs</span>
            </footer>
          </div>
        )}

        {/* Live Execution Console */}
        {loading && (
          <div className="flex-1 flex flex-col items-center justify-center gap-6 py-6 max-w-3xl mx-auto w-full">
            <div
              className="w-full border border-white/15 p-6 rounded-lg flex flex-col gap-4"
              style={glassStyle}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-white flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-red-500" />
                  {progress < 75 ? 'Phase 1: Passive OSINT Enumeration' : 'Phase 2: Local LLM Threat Synthesis & Grounding'}
                </span>
                <span className="text-sm font-bold font-mono text-red-400">{progress}%</span>
              </div>

              <div className="w-full bg-black h-3 rounded-full overflow-hidden border border-white/15 p-0.5">
                <div
                  className="bg-gradient-to-r from-red-600 via-red-500 to-white h-full rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>

              <div className="flex items-center justify-between text-xs text-neutral-400 pt-1 font-mono">
                <span>{loadingText}</span>
                <span className="text-red-400">ID: {jobId ? jobId.substring(0, 8) : '...'}</span>
              </div>
            </div>

            <div className="w-full bg-black/80 border border-white/15 rounded-lg overflow-hidden flex flex-col">
              <div className="bg-neutral-950 px-4 py-2.5 border-b border-white/10 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Terminal className="h-4 w-4 text-red-500" />
                  <span className="text-xs font-mono font-medium text-white">Live Backend Execution Terminal</span>
                </div>
                <span className="text-[10px] font-mono text-red-400 bg-red-600/15 border border-red-500/40 px-2 py-0.5 rounded uppercase tracking-wide">
                  Live Stream
                </span>
              </div>

              <div className="p-4 h-64 overflow-y-auto font-mono text-xs flex flex-col gap-1.5 bg-black/70 text-neutral-300">
                {logs.map((log, index) => (
                  <div key={index} className="flex items-start gap-2.5 leading-relaxed">
                    <span className="text-neutral-600 shrink-0">[{log.timestamp}]</span>
                    <span
                      className={
                        log.level === 'ERROR'
                          ? 'text-red-500 font-bold'
                          : log.level === 'WARN'
                          ? 'text-red-300 font-semibold'
                          : log.level === 'SUCCESS'
                          ? 'text-white font-semibold'
                          : log.level === 'AI'
                          ? 'text-red-400 font-semibold'
                          : 'text-neutral-200'
                      }
                    >
                      {log.msg}
                    </span>
                  </div>
                ))}
                <div ref={consoleEndRef} />
              </div>
            </div>
          </div>
        )}

        {/* Active Results Dashboard */}
        {summaryData && !loading && (
          <>
            {/* Top Target Control Bar */}
            <div
              className="p-4 rounded-lg border border-white/15 flex items-center justify-between flex-wrap gap-3 print:hidden"
              style={glassStyle}
            >
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-xs text-neutral-400 font-medium">Active Target:</span>
                <span className="text-sm font-bold text-white font-mono">{summaryData.target_domain}</span>
                <span className="text-xs text-neutral-500 font-mono">({jobId})</span>
                {hasGroundingWarning ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-red-600/20 text-red-300 border border-red-500/50">
                    <AlertTriangle className="h-3 w-3" /> Grounding Gate Flagged Hallucination
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-white/10 text-white border border-white/25">
                    <CheckCircle2 className="h-3 w-3 text-red-500" /> Grounding Gate Verified
                  </span>
                )}
              </div>
              <form onSubmit={handleStartScan} className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="New target domain..."
                  value={targetDomain || ''}
                  onChange={(e) => setTargetDomain(e.target.value)}
                  className="bg-black/70 text-xs px-3 py-1.5 rounded-lg border border-white/15 focus:outline-none focus:border-red-500 w-56 font-mono text-white"
                />
                <button
                  type="submit"
                  disabled={!targetDomain.trim()}
                  className="bg-white hover:bg-neutral-200 disabled:opacity-40 text-black text-xs px-3 py-1.5 rounded-lg font-bold transition cursor-pointer border-b-2 border-red-600"
                >
                  Scan New Target
                </button>
              </form>
            </div>

            {/* KPI Metric Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="border border-white/15 p-4 rounded-lg" style={glassStyle}>
                <span className="text-[11px] text-neutral-400 uppercase font-semibold tracking-wider">Target Domain</span>
                <p className="text-lg font-bold text-white mt-1 font-mono truncate">{summaryData.target_domain}</p>
              </div>
              <div className="border border-white/15 p-4 rounded-lg" style={glassStyle}>
                <span className="text-[11px] text-neutral-400 uppercase font-semibold tracking-wider">Total Subdomains</span>
                <p className="text-2xl font-bold text-white mt-1">{totalSubdomains}</p>
              </div>
              <div className="border border-white/15 p-4 rounded-lg" style={glassStyle}>
                <span className="text-[11px] text-neutral-400 uppercase font-semibold tracking-wider">Active IPs</span>
                <p className="text-2xl font-bold text-white mt-1">{totalIps}</p>
              </div>
              <div className="border border-red-500/40 p-4 rounded-lg" style={glassStyle}>
                <span className="text-[11px] text-red-400 uppercase font-semibold tracking-wider">Multi-Source Validated</span>
                <p className="text-2xl font-bold text-red-400 mt-1">{highConfCount}</p>
              </div>
            </div>

            {/* View Switcher Tabs */}
            <div className="flex border-b border-white/15 gap-6 print:hidden">
              <button
                onClick={() => setActiveTab('briefing')}
                className={`pb-3 text-sm font-medium border-b-2 transition cursor-pointer ${
                  activeTab === 'briefing'
                    ? 'border-red-500 text-white'
                    : 'border-transparent text-neutral-400 hover:text-white'
                }`}
              >
                Intelligence Report &amp; Asset Analytics
              </button>
              <button
                onClick={() => setActiveTab('graph')}
                className={`pb-3 text-sm font-medium border-b-2 transition cursor-pointer ${
                  activeTab === 'graph'
                    ? 'border-red-500 text-white'
                    : 'border-transparent text-neutral-400 hover:text-white'
                }`}
              >
                Graph Explorer ({rawGraphData.nodes.filter((n) => n.type !== 'DNS_RECORD').length} Total Nodes)
              </button>
              <button
                onClick={() => setActiveTab('logs')}
                className={`pb-3 text-sm font-medium border-b-2 transition flex items-center gap-1.5 cursor-pointer ${
                  activeTab === 'logs'
                    ? 'border-red-500 text-white'
                    : 'border-transparent text-neutral-400 hover:text-white'
                }`}
              >
                <Terminal className="h-3.5 w-3.5 text-red-500" />
                Execution Logs ({logs.length})
              </button>
            </div>

            {/* TAB 1: Executive Summary -> Visual Charts -> Asset Table -> Technical Summary */}
            {activeTab === 'briefing' && (
              <div id="briefing-content" className="flex flex-col gap-6">
                <div className="border border-white/15 rounded-lg p-7" style={glassStyle}>
                  <ReactMarkdown components={markdownComponents}>{execSummary}</ReactMarkdown>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="border border-white/15 rounded-lg p-6 flex flex-col justify-between" style={glassStyle}>
                    <div className="flex items-center gap-2 mb-4">
                      <PieChart className="h-5 w-5 text-red-500" />
                      <h3 style={{ fontFamily: "'Syne', sans-serif" }} className="text-base font-bold text-white">
                        Attack Surface Asset Composition
                      </h3>
                    </div>

                    <div className="flex items-center justify-around my-2">
                      <div
                        className="w-36 h-36 rounded-full flex items-center justify-center"
                        style={{
                          background: `conic-gradient(#f97316 0% ${subPct}%, #ffffff ${subPct}% 100%)`
                        }}
                      >
                        <div className="w-24 h-24 rounded-full bg-[#060606] flex flex-col items-center justify-center border border-white/15">
                          <span className="text-xl font-bold text-white">{totalSubdomains + totalIps}</span>
                          <span className="text-[10px] uppercase text-neutral-400">Total Assets</span>
                        </div>
                      </div>

                      <div className="flex flex-col gap-3 text-sm">
                        <div className="flex items-center gap-2.5">
                          <span className="w-3.5 h-3.5 rounded-sm bg-red-500 inline-block" />
                          <div>
                            <p className="font-semibold text-white">{totalSubdomains} Subdomains ({subPct}%)</p>
                            <p className="text-xs text-neutral-400">Web &amp; DNS endpoints</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2.5">
                          <span className="w-3.5 h-3.5 rounded-sm bg-white inline-block" />
                          <div>
                            <p className="font-semibold text-white">{totalIps} IP Addresses ({ipPct}%)</p>
                            <p className="text-xs text-neutral-400">Routable host infrastructure</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="border border-white/15 rounded-lg p-6 flex flex-col justify-between" style={glassStyle}>
                    <div className="flex items-center gap-2 mb-4">
                      <BarChart3 className="h-5 w-5 text-red-500" />
                      <h3 style={{ fontFamily: "'Syne', sans-serif" }} className="text-base font-bold text-white">
                        Entity Confidence Distribution
                      </h3>
                    </div>

                    <div className="flex flex-col gap-5 my-auto">
                      <div>
                        <div className="flex justify-between text-xs mb-1.5">
                          <span className="text-neutral-200 font-medium">High Confidence (≥ 80% Multi-Tool Correlated)</span>
                          <span className="font-mono text-red-400 font-bold">{highConfCount} ({highConfPct}%)</span>
                        </div>
                        <div className="w-full bg-black h-3.5 rounded-full overflow-hidden border border-white/15">
                          <div className="bg-red-500 h-full rounded-full" style={{ width: `${highConfPct}%` }} />
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between text-xs mb-1.5">
                          <span className="text-neutral-200 font-medium">Standard Confidence (60% Single-Source Observation)</span>
                          <span className="font-mono text-white font-bold">{lowConfCount} ({lowConfPct}%)</span>
                        </div>
                        <div className="w-full bg-black h-3.5 rounded-full overflow-hidden border border-white/15">
                          <div className="bg-neutral-400 h-full rounded-full" style={{ width: `${lowConfPct}%` }} />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="border border-white/15 rounded-lg overflow-hidden" style={glassStyle}>
                  <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-black/60 flex-wrap gap-2">
                    <h3 style={{ fontFamily: "'Syne', sans-serif" }} className="text-base font-bold text-white">
                      Discovered Subdomains, IPs &amp; DNS/WHOIS Inventory
                    </h3>
                    <div className="flex items-center gap-1.5 text-xs">
                      {['ALL', 'SUBDOMAIN', 'IP_ADDRESS', 'DNS_RECORD'].map((type) => (
                        <button
                          key={type}
                          onClick={() => setAssetFilter(type)}
                          className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                            assetFilter === type
                              ? 'bg-red-600 text-white font-bold'
                              : 'bg-neutral-900 text-neutral-400 hover:text-white border border-white/10'
                          }`}
                        >
                          {type === 'ALL'
                            ? 'All'
                            : type === 'SUBDOMAIN'
                            ? 'Subdomains'
                            : type === 'IP_ADDRESS'
                            ? 'IP Addresses'
                            : 'DNS / WHOIS'}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="max-h-80 overflow-y-auto">
                    <table className="w-full text-left border-collapse text-sm">
                      <thead className="bg-black/90 text-xs uppercase text-neutral-400 sticky top-0">
                        <tr>
                          <th className="py-3 px-6 border-b border-white/10">Asset Type</th>
                          <th className="py-3 px-6 border-b border-white/10">Discovered Host / IP / Record</th>
                          <th className="py-3 px-6 border-b border-white/10">Confidence Score</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.06] font-mono text-xs">
                        {filteredEntities.length === 0 ? (
                          <tr>
                            <td colSpan="3" className="py-6 text-center text-neutral-500">
                              No entity records available.
                            </td>
                          </tr>
                        ) : (
                          filteredEntities.map((item, i) => {
                            const confPct = Math.round((item.confidence || 0.6) * 100);
                            const isHigh = confPct >= 80;
                            return (
                              <tr key={item.id || i} className="hover:bg-white/[0.04] transition">
                                <td className="py-2.5 px-6">
                                  {item.type === 'IP_ADDRESS' ? (
                                    <span className="inline-flex items-center gap-1.5 text-white bg-white/10 border border-white/25 px-2 py-0.5 rounded">
                                      <Server className="h-3 w-3 text-red-400" /> IP_ADDRESS
                                    </span>
                                  ) : item.type === 'DNS_RECORD' ? (
                                    <span className="inline-flex items-center gap-1.5 text-red-300 bg-red-600/15 border border-red-500/40 px-2 py-0.5 rounded">
                                      <FileCode2 className="h-3 w-3 text-red-400" /> DNS_RECORD
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1.5 text-neutral-200 bg-neutral-900 border border-white/15 px-2 py-0.5 rounded">
                                      <Globe className="h-3 w-3 text-white" /> SUBDOMAIN
                                    </span>
                                  )}
                                </td>
                                <td className="py-2.5 px-6 text-neutral-200 break-all">
                                  <div>{item.value}</div>
                                  {item.type === 'IP_ADDRESS' && item.asn && (
                                    <div className="mt-1 text-[10px] text-neutral-400">
                                      {item.asn}
                                      {item.asn_cidr ? ` · ${item.asn_cidr}` : ''}
                                      {item.provider ? ` · ${item.provider}` : ''}
                                    </div>
                                  )}
                                  {(item.record_type === 'CNAME' || item.service_provider || item.third_party) && (
                                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-neutral-400">
                                      {item.record_type === 'CNAME' && item.cname_target && (
                                        <span>CNAME → {item.cname_target}</span>
                                      )}
                                      {item.service_providers?.length > 0 && (
                                        <span className="text-orange-300">
                                          {item.service_providers.join(', ')}
                                        </span>
                                      )}
                                      {item.third_party && <span>EXTERNAL</span>}
                                      {item.dangling && (
                                        <span className="rounded border border-red-500/50 px-1 text-red-300">
                                          NXDOMAIN — REVIEW
                                        </span>
                                      )}
                                    </div>
                                  )}
                                </td>
                                <td className="py-2.5 px-6">
                                  <span
                                    className={`px-2 py-0.5 rounded font-semibold ${
                                      isHigh
                                        ? 'bg-red-600/20 text-red-300 border border-red-500/45'
                                        : 'bg-neutral-900 text-neutral-300 border border-white/15'
                                    }`}
                                  >
                                    {confPct}% ({item.type === 'DNS_RECORD' ? 'Authoritative' : isHigh ? 'Correlated' : 'Single-Source'})
                                  </span>
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {techSummary && (
                  <div className="border border-white/15 rounded-lg p-7" style={glassStyle}>
                    <ReactMarkdown components={markdownComponents}>{techSummary}</ReactMarkdown>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: BloodHound-Style Interactive Graph Explorer */}
            {activeTab === 'graph' && (
              <div className="flex flex-col gap-3">
                <div
                  className="border border-white/15 rounded-lg px-4 py-3 flex items-center justify-between flex-wrap gap-3 relative z-30 isolate"
                  style={glassStyle}
                >
                  <div className="flex items-center gap-3 flex-1 min-w-[280px] relative">
                    <div className="relative flex-1 max-w-md">
                      <Search className="h-4 w-4 text-red-500 absolute left-3 top-2.5" />
                      <input
                        type="text"
                        placeholder="Search node (e.g. epayment, imail, 113.23.129)..."
                        value={graphSearch}
                        onChange={(e) => {
                          setGraphSearch(e.target.value);
                          setFocusNodeId(null);
                        }}
                        className="w-full bg-black/80 border border-white/15 rounded-lg pl-9 pr-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-red-500"
                      />

                      {searchSuggestions.length > 0 && !focusNodeId && (
                        <div className="absolute left-0 right-0 top-9 bg-neutral-950 border border-red-500/40 rounded-lg shadow-2xl z-50 overflow-hidden">
                          {searchSuggestions.map((s) => (
                            <button
                              key={s.id}
                              type="button"
                              onClick={() => {
                                setFocusNodeId(String(s.id));
                                setGraphSearch(s.label);
                              }}
                              className="w-full text-left px-3 py-2 text-xs font-mono hover:bg-neutral-800 flex items-center justify-between border-b border-white/5 last:border-none cursor-pointer"
                            >
                              <span className="text-white truncate">
                                {s.label}
                                {s.subnet_cidr ? ` [${s.subnet_cidr}]` : ''}
                              </span>
                              <span className="text-[10px] text-red-400 ml-2 shrink-0">{s.type}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {(focusNodeId || graphSearch) && (
                      <button
                        onClick={() => {
                          setFocusNodeId(null);
                          setGraphSearch('');
                          setSelectedNodeInfo(null);
                        }}
                        className="bg-neutral-900 hover:bg-neutral-800 text-xs px-3 py-1.5 rounded-lg text-white flex items-center gap-1.5 border border-white/15 cursor-pointer"
                      >
                        <RotateCcw className="h-3.5 w-3.5 text-red-500" /> Reset Cluster View
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-4 text-[11px] font-mono flex-wrap">
                    <span className="flex items-center gap-1.5 text-red-400">
                      <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" />
                      C001: RESOLVES_TO
                    </span>
                    <span className="flex items-center gap-1.5 text-white">
                      <span className="w-2.5 h-2.5 rounded-full bg-white inline-block" />
                      C003: SHARES_IP
                    </span>
                    <span className="flex items-center gap-1.5 text-neutral-400">
                      <span className="w-2.5 h-2.5 rounded-full bg-neutral-500 inline-block" />
                      C005: /24 SUBNET
                    </span>
                    <span className="text-neutral-500">Click any node to isolate</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
                  <div
                    style={{ height: '620px' }}
                    className={`${
                      selectedNodeInfo ? 'lg:col-span-3' : 'lg:col-span-4'
                    } bg-[#060606] border border-white/15 rounded-lg overflow-hidden relative`}
                  >
                    {nodes.length === 0 ? (
                      <div className="w-full h-full flex items-center justify-center text-neutral-400 text-sm">
                        No matching topology nodes found.
                      </div>
                    ) : (
                      <ReactFlow
                        key={`${jobId}-${focusNodeId || graphSearch || 'clusters'}`}
                        nodes={nodes}
                        edges={edges}
                        onNodeClick={(_, node) => {
                          setFocusNodeId(String(node.id));
                          if (node.data?.rawNode) {
                            setSelectedNodeInfo(node.data.rawNode);
                          }
                        }}
                        fitView
                      >
                        <Background color="#262626" gap={20} />
                        <Controls />
                        <MiniMap
                          nodeColor={(n) =>
                            n.data?.label?.startsWith('TARGET:')
                              ? '#ffffff'
                              : n.data?.label?.startsWith('IP:')
                              ? '#f97316'
                              : '#525252'
                          }
                          style={{ background: '#0a0a0a' }}
                        />
                      </ReactFlow>
                    )}
                  </div>

                  {selectedNodeInfo && (
                    <div className="bg-neutral-950 border border-red-500/35 rounded-lg p-4 flex flex-col gap-4 h-[620px] overflow-y-auto">
                      <div className="flex items-center justify-between border-b border-white/10 pb-3">
                        <div className="flex items-center gap-2">
                          <Crosshair className="h-4 w-4 text-red-500" />
                          <h3 className="text-xs font-bold uppercase tracking-wider text-white">Node Inspector</h3>
                        </div>
                        <button
                          onClick={() => setSelectedNodeInfo(null)}
                          className="text-xs text-neutral-400 hover:text-white cursor-pointer"
                        >
                          ✕
                        </button>
                      </div>

                      <div className="flex flex-col gap-2 text-xs font-mono">
                        <div>
                          <span className="text-neutral-500 block">ENTITY VALUE</span>
                          <span className="text-white font-semibold break-all">{selectedNodeInfo.label}</span>
                        </div>
                        <div className="flex justify-between pt-1">
                          <span className="text-neutral-500">TYPE:</span>
                          <span className="text-neutral-200">{selectedNodeInfo.type}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-neutral-500">CONFIDENCE:</span>
                          <span className="text-red-400 font-bold">
                            {Math.round((selectedNodeInfo.confidence || 0.6) * 100)}%
                          </span>
                        </div>
                        {selectedNodeInfo.subnet_cidr && (
                          <div className="flex justify-between">
                            <span className="text-neutral-500">SUBNET (C005):</span>
                            <span className="text-white">{selectedNodeInfo.subnet_cidr}</span>
                          </div>
                        )}
                        {selectedNodeInfo.asn && (
                          <>
                            <div className="flex justify-between gap-3">
                              <span className="text-neutral-500">ASN:</span>
                              <span className="text-white text-right">{selectedNodeInfo.asn}</span>
                            </div>
                            {selectedNodeInfo.asn_cidr && (
                              <div className="flex justify-between gap-3">
                                <span className="text-neutral-500">ASN PREFIX:</span>
                                <span className="text-white text-right">{selectedNodeInfo.asn_cidr}</span>
                              </div>
                            )}
                            {selectedNodeInfo.provider && (
                              <div className="flex justify-between gap-3">
                                <span className="text-neutral-500">NETWORK:</span>
                                <span className="text-white text-right break-all">{selectedNodeInfo.provider}</span>
                              </div>
                            )}
                          </>
                        )}
                        {selectedNodeInfo.corroborated_by?.length > 0 && (
                          <div className="pt-1">
                            <span className="text-neutral-500 block mb-1">OSINT SOURCES (C004):</span>
                            <div className="flex flex-wrap gap-1">
                              {selectedNodeInfo.corroborated_by.map((src) => (
                                <span
                                  key={src}
                                  className="px-2 py-0.5 bg-red-600/15 border border-red-500/35 rounded text-[10px] text-red-200"
                                >
                                  {src}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="border-t border-white/10 pt-3 flex flex-col gap-2">
                        <span className="text-[11px] font-bold uppercase text-neutral-400">
                          Correlated Edges ({selectedNodeEdges.length})
                        </span>
                        <div className="flex flex-col gap-1.5">
                          {selectedNodeEdges.slice(0, 20).map((edge, idx) => {
                            const isSource = String(edge.source) === String(selectedNodeInfo.id);
                            const peerId = isSource ? edge.target : edge.source;
                            const peerNode = rawGraphData.nodes.find((n) => String(n.id) === String(peerId));
                            return (
                              <button
                                key={idx}
                                onClick={() => setFocusNodeId(String(peerId))}
                                className="text-left bg-black/70 hover:bg-neutral-900 border border-white/10 rounded-lg p-2 text-[11px] font-mono transition cursor-pointer"
                              >
                                <div className="flex items-center justify-between text-[10px] mb-0.5">
                                  <span className="text-red-400 font-bold">{edge.rule_id}</span>
                                  <span className="text-neutral-400">{edge.relationship}</span>
                                </div>
                                <div className="text-neutral-200 truncate">
                                  {peerNode ? peerNode.label : peerId}
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB 3: Persistent Execution Terminal Logs */}
            {activeTab === 'logs' && (
              <div
                className="border border-white/15 rounded-lg overflow-hidden flex flex-col"
                style={glassStyle}
              >
                <div className="bg-neutral-950 px-5 py-3 border-b border-white/10 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <Terminal className="h-4 w-4 text-red-500" />
                    <span className="text-xs font-mono font-semibold text-white">
                      Pipeline Execution Audit Trail — Job {jobId}
                    </span>
                  </div>
                  <button
                    onClick={handleCopyLogs}
                    disabled={logs.length === 0}
                    className="bg-neutral-900 hover:bg-neutral-800 disabled:opacity-40 text-xs px-3 py-1 rounded-lg text-white flex items-center gap-1.5 border border-white/15 transition cursor-pointer"
                  >
                    {copiedLogs ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-red-400" /> Copied
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5 text-red-400" /> Copy Logs
                      </>
                    )}
                  </button>
                </div>

                <div className="p-5 h-[480px] overflow-y-auto font-mono text-xs flex flex-col gap-2 bg-black/70 text-neutral-300">
                  {logs.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-neutral-500">
                      No execution logs recorded for this session. Run a scan to capture live pipeline events.
                    </div>
                  ) : (
                    logs.map((log, index) => (
                      <div key={index} className="flex items-start gap-3 leading-relaxed border-b border-white/[0.05] pb-1.5">
                        <span className="text-neutral-600 shrink-0">[{log.timestamp}]</span>
                        <span
                          className={
                            log.level === 'ERROR'
                              ? 'text-red-500 font-bold'
                              : log.level === 'WARN'
                              ? 'text-red-300 font-semibold'
                              : log.level === 'SUCCESS'
                              ? 'text-white font-semibold'
                              : log.level === 'AI'
                              ? 'text-red-400 font-semibold'
                              : 'text-neutral-200'
                          }
                        >
                          {log.msg}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}