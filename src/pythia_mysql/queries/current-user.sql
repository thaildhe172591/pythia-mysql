-- Purpose: the account MySQL authenticated this session as: a routine created
--          without DEFINER is defined by it
-- Binds:   none
-- Returns: ACCOUNT
select current_user() as account
