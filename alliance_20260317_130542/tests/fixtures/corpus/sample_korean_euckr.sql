-- 한국어 주석이 포함된 SQL 파일
-- 데이터베이스: 주식분석

CREATE TABLE [dbo].[tbl_day_chart](
    [code] [varchar](7) NOT NULL,
    [종가] [int] NULL,
    [시가] [int] NULL,
    [고가] [int] NULL,
    [저가] [int] NULL,
    [거래량] [bigint] NULL
);

EXEC sys.sp_addextendedproperty @name=N'MS_DESCRIPTION', @value=N'종목코드', @level0type=N'SCHEMA',@level0name=N'dbo', @level1type=N'TABLE',@level1name=N'tbl_day_chart', @level2type=N'COLUMN',@level2name=N'code';
EXEC sys.sp_addextendedproperty @name=N'MS_DESCRIPTION', @value=N'종가', @level0type=N'SCHEMA',@level0name=N'dbo', @level1type=N'TABLE',@level1name=N'tbl_day_chart', @level2type=N'COLUMN',@level2name=N'종가';
EXEC sys.sp_addextendedproperty @name=N'MS_DESCRIPTION', @value=N'일별 차트 데이터', @level0type=N'SCHEMA',@level0name=N'dbo', @level1type=N'TABLE',@level1name=N'tbl_day_chart';
