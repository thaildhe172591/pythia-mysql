-- Purpose: how many rows an UPDATE's or DELETE's own WHERE selects, and a
--          fingerprint that moves when any of them changes (order-independent)
-- Binds:   none: the target, the row and the predicate are spliced in, the
--          statement's own text
-- Returns: N, FINGERPRINT
select count(*) as n,
       coalesce(sum(cast(conv(left(md5(/*ROW*/), 15), 16, 10) as unsigned)), 0) as fingerprint
  from /*TARGET*/
 where /*WHERE*/
