-- Summary by skilled visa subclass, stream and occupation list.
SELECT *
FROM visa_occupation_summary;

-- Find all visa/list records for an ANZSCO code.
SELECT
  visa_subclass,
  visa_name,
  visa_stream,
  list_code,
  occupation_title,
  anzsco_code,
  assessing_authority,
  applicable_circumstance_code
FROM occupation_records
WHERE anzsco_code = '261313'
ORDER BY CAST(visa_subclass AS INTEGER), visa_stream, list_code;

-- Search occupation title across all skilled visa occupation records.
SELECT
  occupation_title,
  anzsco_code,
  visa_subclass,
  visa_stream,
  list_code,
  assessing_authority_expanded
FROM occupation_records
WHERE occupation_title LIKE '%software%'
ORDER BY occupation_title, CAST(visa_subclass AS INTEGER);

-- List all Home Affairs visa-list items in category order.
SELECT
  c.name AS category,
  v.name AS visa_name,
  GROUP_CONCAT(s.subclass, ', ') AS subclasses,
  v.status,
  v.official_url
FROM visas v
JOIN visa_categories c ON c.id = v.category_id
LEFT JOIN visa_subclasses s ON s.visa_id = v.id
GROUP BY v.id
ORDER BY c.sort_order, v.id;

-- Show source documents behind a given visa subclass.
SELECT DISTINCT
  r.visa_subclass,
  r.visa_stream,
  r.list_code,
  s.title,
  s.register_id,
  s.effective_from,
  s.official_url
FROM occupation_records r
JOIN sources s ON s.id = r.source_id
WHERE r.visa_subclass = '482'
ORDER BY r.visa_stream, r.list_code;
