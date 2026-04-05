import { Message, Asset } from './types';

export const INITIAL_MESSAGES: Message[] = [
  {
    id: '1',
    role: 'operator',
    timestamp: '14:22:01',
    content: '프로젝트 옵시디언 아키텍처와 관련된 모든 문서를 검색하고 최근 HWP 보안 감사 결과와 대조해 줘.'
  },
  {
    id: '2',
    role: 'architect',
    timestamp: '14:22:04',
    content: '중앙 저장소 스캔 중... 관련성 높은 자산 4개를 발견했습니다. 현재 교차 참조 보고서를 합성하고 있습니다. 보안 프로토콜이 활성화되었습니다.'
  },
  {
    id: '3',
    role: 'operator',
    timestamp: '14:23:45',
    content: 'PDF에 언급된 암호화 키를 추출하여 DOCX 사양과 비교해 줘.'
  }
];

export const ASSETS: Asset[] = [
  {
    id: 'obsidian-pdf',
    type: 'pdf',
    name: '옵시디언_코어_v1.pdf',
    size: '2.4 MB',
    status: '암호화 세그먼트 감지됨',
    matchPrecision: '98.4%'
  },
  {
    id: 'site-blueprint',
    type: 'image',
    name: '사이트_청사진_09.png',
    description: 'Tier-3 데이터 센터 냉각 노드의 구조적 분석.',
    imageUrl: 'https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&q=80&w=1000',
    matchPrecision: '95.2%'
  },
  {
    id: 'security-memo',
    type: 'docx',
    name: '보안_메모.docx',
    size: '12 KB',
    matchPrecision: '88.2%'
  },
  {
    id: 'audit-log',
    type: 'hwp',
    name: '레거시_감사_로그.hwp',
    description: 'Arch-v2 번역 모듈이 필요한 레거시 문서입니다. 변환을 승인해 주세요.',
    status: '레거시 포맷',
    matchPrecision: '74.5%'
  }
];
