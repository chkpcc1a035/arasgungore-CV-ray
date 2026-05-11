# eMPF Platform Overview

The eMPF Platform is a central electronic platform developed under the
Mandatory Provident Fund Schemes Authority (MPFA) to standardise,
streamline and automate the administration work of all MPF schemes
in Hong Kong.

## Scope

The platform handles administration for approximately 4.7 million MPF
scheme members and their employers. It centralises functions that were
previously performed separately by each MPF trustee, including:

- Member enrolment and account management
- Contribution processing
- Investment instruction processing
- Benefit payment processing
- Statement generation and member communication

## Rollout

The eMPF Platform rollout follows a phased onboarding approach. MPF
trustees migrate to the platform in batches, with the full migration
expected to complete by 2025. Each trustee onboarding involves data
migration, parallel-run testing, and a cutover window.

## Technology stack

The platform is built on a private cloud infrastructure using Red Hat
OpenShift for container orchestration, with Oracle Database for the
core transactional store. Application delivery uses Jenkins-based CI/CD
pipelines, Nginx as the edge layer, and MuleSoft as the API gateway.
Authentication and authorisation are handled via Red Hat Directory
Server and Red Hat Single Sign-On (RHSSO).

## Expected benefits

The MPFA estimates that the eMPF Platform will reduce the administration
cost of MPF schemes by 30% over a 10-year period, with these savings
ultimately passed through to scheme members in the form of lower fees.
