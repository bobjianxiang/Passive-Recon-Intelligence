import html2pdf from 'html2pdf.js';
import { Document, Packer, Paragraph, TextRun, HeadingLevel } from 'docx';
import { saveAs } from 'file-saver';

// Export rendered Markdown view to PDF
export const exportToPDF = (elementId, filename = 'executive-briefing.pdf') => {
  const element = document.getElementById(elementId);
  if (!element) return;
  const options = {
    margin: 0.5,
    filename: filename,
    image: { type: 'jpeg', quality: 0.98 },
    html2canvas: { scale: 2 },
    jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
  };
  html2pdf().set(options).from(element).save();
};

// Export Markdown text content to DOCX
export const exportToDocx = async (markdownText, filename = 'executive-briefing.docx') => {
  if (!markdownText) return;
  const lines = markdownText.split('\n');
  const children = [];

  lines.forEach(line => {
    if (line.startsWith('# ')) {
      children.push(new Paragraph({
        text: line.replace('# ', ''),
        heading: HeadingLevel.HEADING_1,
      }));
    } else if (line.startsWith('## ')) {
      children.push(new Paragraph({
        text: line.replace('## ', ''),
        heading: HeadingLevel.HEADING_2,
      }));
    } else if (line.startsWith('- ')) {
      children.push(new Paragraph({
        text: line.replace('- ', ''),
        bullet: { level: 0 }
      }));
    } else if (line.trim() !== '') {
      children.push(new Paragraph({
        children: [new TextRun(line)]
      }));
    }
  });

  const doc = new Document({
    sections: [{ properties: {}, children }]
  });

  const blob = await Packer.toBlob(doc);
  saveAs(blob, filename);
};