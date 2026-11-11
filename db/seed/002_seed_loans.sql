-- LoanTrack Seed 002: Initial sample loans
-- 6 seed records with varied cities and lifecycle statuses (PENDING, APPROVED, REJECTED)

INSERT INTO loans (borrower_name, loan_amount, property_city, status, created_at) VALUES
  ('Alice Johnson', 350000.00, 'Seattle', 'APPROVED', now() - INTERVAL '5 days'),
  ('Bob Smith', 480000.00, 'Austin', 'PENDING', now() - INTERVAL '4 days'),
  ('Carlos Rodriguez', 275000.00, 'Denver', 'APPROVED', now() - INTERVAL '3 days'),
  ('Diana Prince', 620000.00, 'San Francisco', 'REJECTED', now() - INTERVAL '2 days'),
  ('Ethan Hunt', 510000.00, 'Chicago', 'PENDING', now() - INTERVAL '1 day'),
  ('Fiona Gallagher', 195000.00, 'Boston', 'APPROVED', now());
