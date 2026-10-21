-- Purpose: the first rows an UPDATE's or DELETE's own WHERE selects, to show
--          (one more than shown, so the preview can say it was cut)
-- Binds:   none: the target and the predicate are spliced in, the statement's
--          own text
-- Returns: every column of the target
select * from /*TARGET*/ where /*WHERE*/ limit 11
